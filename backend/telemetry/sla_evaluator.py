import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.core.config import settings
from backend.telemetry.collector import get_telemetry_collector

logger = logging.getLogger(__name__)

COMPARISON_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

PRIORITY_INTERVALS = {
    "high": settings.sla_default_interval_high,
    "medium": settings.sla_default_interval_medium,
    "low": settings.sla_default_interval_low,
}


class SLAEvaluator:
    def __init__(self):
        self._periodic_task: Optional[asyncio.Task] = None
        self._evaluation_results: dict[int, dict] = {}
        self._dynamic_intervals: dict[int, int] = {}
        self._per_intent_tasks: dict[int, asyncio.Task] = {}
        self._historical_metrics: dict[int, list[dict]] = {}

    @staticmethod
    def _normalize_sla_conditions(sla_conditions) -> list[dict]:
        """Convert flat dict format to list[dict] format for SLA evaluation.

        Supports both formats:
        - Flat dict: {"target_device": "X", "metric_type": "bandwidth", "threshold": 500, "unit": "Mbps"}
        - List[dict]: [{"metric": "bandwidth", "device": "X", "op": ">=", "value": 500}]
        """
        if isinstance(sla_conditions, list):
            return sla_conditions
        if not isinstance(sla_conditions, dict):
            return []

        # Check if it's already in list[dict] format (has metric/device/op/value keys)
        if any(k in sla_conditions for k in ("metric", "device", "op", "value")):
            return [sla_conditions]

        # Convert flat dict format to list[dict] format
        target_device = sla_conditions.get("target_device", "")
        metric_type = sla_conditions.get("metric_type", "")
        threshold = sla_conditions.get("threshold", 0)
        unit = sla_conditions.get("unit", "")

        if not metric_type:
            return []

        # Determine comparison operator based on metric type
        if metric_type in ("bandwidth", "priority", "access"):
            op = ">="  # bandwidth/priority/access should be >= threshold
        elif metric_type in ("latency", "jitter", "packet_loss"):
            op = "<="  # latency/jitter/packet_loss should be <= threshold
        else:
            op = ">="

        return [{
            "metric": metric_type,
            "device": target_device,
            "op": op,
            "value": threshold,
            "unit": unit,
        }]

    async def evaluate_intent_sla(
        self,
        intent_id: int,
        sla_conditions: list[dict],
        current_metrics: dict[str, dict],
    ) -> dict:
        violations = []
        evaluated_at = datetime.now(timezone.utc).isoformat()

        # Normalize sla_conditions to list[dict] format
        normalized_conditions = self._normalize_sla_conditions(sla_conditions)

        for condition in normalized_conditions:
            metric = condition.get("metric", "")
            device = condition.get("device", "")
            op = condition.get("op", ">=")
            threshold = condition.get("value", 0)

            device_metrics = current_metrics.get(device, {})
            actual_value = device_metrics.get(metric)

            if actual_value is None:
                violations.append({
                    "condition": condition,
                    "actual_value": None,
                    "reason": f"metric '{metric}' not found for device '{device}'",
                })
                continue

            compare_fn = COMPARISON_OPS.get(op)
            if compare_fn is None:
                violations.append({
                    "condition": condition,
                    "actual_value": actual_value,
                    "reason": f"unsupported operator '{op}'",
                })
                continue

            if not compare_fn(actual_value, threshold):
                violations.append({
                    "condition": condition,
                    "actual_value": actual_value,
                    "threshold": threshold,
                    "operator": op,
                    "reason": f"{metric}={actual_value} violates {op} {threshold}",
                })

        if violations:
            sla_status = "DEVIATING"
        else:
            sla_status = "ACHIEVING"

        result = {
            "sla_status": sla_status,
            "violations": violations,
            "evaluated_at": evaluated_at,
        }

        self._evaluation_results[intent_id] = result
        self._store_historical_metrics(intent_id, current_metrics)
        return result

    def _store_historical_metrics(self, intent_id: int, metrics: dict):
        if intent_id not in self._historical_metrics:
            self._historical_metrics[intent_id] = []
        self._historical_metrics[intent_id].append(metrics)
        max_history = 180
        if len(self._historical_metrics[intent_id]) > max_history:
            self._historical_metrics[intent_id] = self._historical_metrics[intent_id][-max_history:]

    def get_historical_metrics(self, intent_id: int) -> list[dict]:
        return self._historical_metrics.get(intent_id, [])

    async def evaluate_all_intents(self) -> dict[int, dict]:
        from backend.database.connection import async_session_maker
        from backend.database.models import Intent
        from sqlalchemy import select

        collector = get_telemetry_collector()
        current_metrics = await collector.collect_all_devices()

        results = {}
        async with async_session_maker() as session:
            result = await session.execute(
                select(Intent).where(
                    Intent.execution_status.in_(["executed", "approved_pending_execution"]),
                    Intent.sla_conditions.isnot(None),
                )
            )
            intents = result.scalars().all()

            # Batch evaluation: collect all updates first, then single commit
            from backend.database.models import SLAEvaluationResult
            db_results_to_add = []

            for intent in intents:
                sla_conditions = intent.sla_conditions
                if not sla_conditions:
                    continue

                evaluation = await self.evaluate_intent_sla(
                    intent_id=intent.id,
                    sla_conditions=sla_conditions,
                    current_metrics=current_metrics,
                )

                # Track previous SLA status for change notification
                previous_status = intent.sla_status
                intent.sla_status = evaluation["sla_status"]
                intent.last_evaluation_time = datetime.now(timezone.utc)

                # Queue SLA evaluation result for batch insert
                try:
                    db_result = SLAEvaluationResult(
                        intent_id=intent.id,
                        sla_status=evaluation["sla_status"],
                        violations=evaluation.get("violations", []),
                        metrics_snapshot=current_metrics if isinstance(current_metrics, dict) else {},
                    )
                    db_results_to_add.append(db_result)
                except Exception as db_err:
                    logger.warning(f"Failed to create SLA result for intent {intent.id}: {db_err}")

                results[intent.id] = evaluation

                # Notify on SLA status change
                if previous_status != evaluation["sla_status"] and previous_status is not None:
                    try:
                        from backend.agents.proactive_notifier import get_proactive_notifier
                        notifier = get_proactive_notifier()
                        await notifier.notify_sla_warning(
                            intent_id=intent.id,
                            intent_name=intent.intent_name,
                            metric=sla_conditions.get("metric_type", "unknown") if isinstance(sla_conditions, dict) else "unknown",
                            current_value=str(evaluation.get("violations", [])),
                            threshold=str(sla_conditions.get("threshold", "")) if isinstance(sla_conditions, dict) else "",
                        )
                    except Exception as notify_err:
                        logger.debug(f"SLA change notification failed: {notify_err}")

            # Single batch commit: add all results then commit once
            if db_results_to_add:
                session.add_all(db_results_to_add)
            await session.commit()

        return results

    async def evaluate_with_prediction(self, intent_id: int) -> dict:
        from backend.database.connection import async_session_maker
        from backend.database.models import Intent
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(Intent).where(Intent.id == intent_id)
            )
            intent = result.scalar_one_or_none()

        if intent is None:
            return {"error": f"Intent {intent_id} not found"}

        sla_conditions = intent.sla_conditions
        if not sla_conditions:
            return {"error": f"Intent {intent_id} has no SLA conditions"}

        collector = get_telemetry_collector()
        current_metrics = await collector.collect_all_devices()

        evaluation = await self.evaluate_intent_sla(
            intent_id=intent_id,
            sla_conditions=sla_conditions,
            current_metrics=current_metrics,
        )

        prediction = None
        if settings.sla_prediction_enabled:
            from backend.telemetry.sla_predictor import get_sla_predictor
            predictor = get_sla_predictor()
            historical = self.get_historical_metrics(intent_id)
            prediction = await predictor.predict_violation(
                intent_id=intent_id,
                sla_conditions=sla_conditions,
                historical_metrics=historical,
            )

        return {
            "evaluation": evaluation,
            "prediction": {
                "predicted_violation": prediction.predicted_violation,
                "violation_probability": prediction.violation_probability,
                "predicted_time": prediction.predicted_time.isoformat() if prediction.predicted_time else None,
                "prediction_model": prediction.prediction_model,
                "confidence": prediction.confidence,
                "metrics_forecast": prediction.metrics_forecast,
            } if prediction else None,
        }

    def _get_priority_for_intent(self, intent_id: int) -> str:
        try:
            from backend.database.connection import async_session_maker
            from backend.database.models import Intent
            from sqlalchemy import select
            import asyncio

            async def _fetch():
                async with async_session_maker() as session:
                    result = await session.execute(
                        select(Intent).where(Intent.id == intent_id)
                    )
                    intent = result.scalar_one_or_none()
                    if intent and intent.structured_params:
                        return intent.structured_params.get("priority", "medium")
                return "medium"

            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    priority = loop.run_in_executor(pool, lambda: asyncio.run(_fetch()))
                    return "medium"
            except RuntimeError:
                pass
        except Exception:
            pass
        return "medium"

    def get_dynamic_intervals(self) -> dict:
        all_intervals = {}
        for intent_id, interval in self._dynamic_intervals.items():
            all_intervals[intent_id] = {
                "interval_seconds": interval,
                "source": "custom",
            }

        from backend.database.connection import async_session_maker
        from backend.database.models import Intent
        from sqlalchemy import select
        import asyncio

        async def _fetch_intents():
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Intent).where(
                        Intent.execution_status.in_(["executed", "approved_pending_execution"]),
                        Intent.sla_conditions.isnot(None),
                    )
                )
                return result.scalars().all()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for intent_id in list(self._dynamic_intervals.keys()):
                    pass
            else:
                intents = loop.run_until_complete(_fetch_intents())
                for intent in intents:
                    if intent.id not in self._dynamic_intervals:
                        priority = "medium"
                        if intent.structured_params:
                            priority = intent.structured_params.get("priority", "medium")
                        interval = PRIORITY_INTERVALS.get(priority, settings.sla_default_interval_medium)
                        all_intervals[intent.id] = {
                            "interval_seconds": interval,
                            "source": f"priority:{priority}",
                        }
        except RuntimeError:
            pass

        return all_intervals

    def set_intent_interval(self, intent_id: int, interval_seconds: int):
        self._dynamic_intervals[intent_id] = interval_seconds
        if intent_id in self._per_intent_tasks:
            task = self._per_intent_tasks.pop(intent_id)
            if not task.done():
                task.cancel()

    async def start_periodic_evaluation(self, interval_seconds: int = 30):
        if self._periodic_task and not self._periodic_task.done():
            return

        async def _periodic_loop():
            while True:
                try:
                    await self.evaluate_all_intents()
                except Exception as e:
                    logger.error(f"Periodic SLA evaluation failed: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)

        self._periodic_task = asyncio.create_task(_periodic_loop())
        logger.info(f"Periodic SLA evaluation started with interval {interval_seconds}s")

    async def start_dynamic_periodic_evaluation(self):
        if self._periodic_task and not self._periodic_task.done():
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass

        for task in self._per_intent_tasks.values():
            if not task.done():
                task.cancel()
        self._per_intent_tasks.clear()

        from backend.database.connection import async_session_maker
        from backend.database.models import Intent
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(Intent).where(
                    Intent.execution_status.in_(["executed", "approved_pending_execution"]),
                    Intent.sla_conditions.isnot(None),
                )
            )
            intents = result.scalars().all()

            for intent in intents:
                priority = "medium"
                if intent.structured_params:
                    priority = intent.structured_params.get("priority", "medium")

                interval = self._dynamic_intervals.get(
                    intent.id,
                    PRIORITY_INTERVALS.get(priority, settings.sla_default_interval_medium),
                )

                task = asyncio.create_task(
                    self._per_intent_evaluation_loop(intent.id, interval)
                )
                self._per_intent_tasks[intent.id] = task

        logger.info(f"Dynamic periodic SLA evaluation started for {len(self._per_intent_tasks)} intents")

    async def _per_intent_evaluation_loop(self, intent_id: int, interval_seconds: int):
        while True:
            try:
                await self.evaluate_with_prediction(intent_id)
            except Exception as e:
                logger.error(f"Per-intent SLA evaluation failed for intent {intent_id}: {e}", exc_info=True)
            await asyncio.sleep(interval_seconds)

    async def stop_periodic_evaluation(self):
        if self._periodic_task and not self._periodic_task.done():
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            logger.info("Periodic SLA evaluation stopped")

        for intent_id, task in self._per_intent_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._per_intent_tasks.clear()
        logger.info("All per-intent periodic evaluations stopped")

    def get_evaluation_results(self) -> dict[int, dict]:
        return dict(self._evaluation_results)


_evaluator_instance: Optional[SLAEvaluator] = None


def get_sla_evaluator() -> SLAEvaluator:
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = SLAEvaluator()
    return _evaluator_instance
