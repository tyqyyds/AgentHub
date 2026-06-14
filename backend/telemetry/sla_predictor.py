import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    intent_id: int
    predicted_violation: bool
    violation_probability: float
    predicted_time: Optional[datetime] = None
    prediction_model: str = "statistical"
    confidence: float = 0.0
    metrics_forecast: Optional[dict] = field(default_factory=dict)


class SLAPredictor:
    def __init__(self):
        self._predictions: dict[int, PredictionResult] = {}

    async def predict_violation(
        self,
        intent_id: int,
        sla_conditions: list[dict],
        historical_metrics: list[dict],
    ) -> PredictionResult:
        metric_histories = self._extract_metric_histories(sla_conditions, historical_metrics)

        best_result = None
        for metric_key, history_values in metric_histories.items():
            if len(history_values) < 3:
                continue

            result = self._try_predict_chain(history_values)
            if result is None:
                continue

            threshold = self._get_threshold_for_metric(metric_key, sla_conditions)
            violation_prob = self._calculate_violation_probability(
                result, threshold, sla_conditions, metric_key
            )

            predicted_violation = violation_prob >= settings.sla_alert_threshold

            if predicted_violation:
                predicted_time = self._estimate_violation_time(
                    history_values, result, threshold
                )
            else:
                predicted_time = None

            if best_result is None or violation_prob > best_result.violation_probability:
                best_result = PredictionResult(
                    intent_id=intent_id,
                    predicted_violation=predicted_violation,
                    violation_probability=round(violation_prob, 4),
                    predicted_time=predicted_time,
                    prediction_model=result.get("model", "statistical"),
                    confidence=round(result.get("confidence", 0.0), 4),
                    metrics_forecast=result.get("forecast", {}),
                )

        if best_result is None:
            best_result = PredictionResult(
                intent_id=intent_id,
                predicted_violation=False,
                violation_probability=0.0,
                predicted_time=None,
                prediction_model="none",
                confidence=0.0,
                metrics_forecast={},
            )

        self._predictions[intent_id] = best_result
        await self._persist_prediction(best_result)

        if best_result.predicted_violation:
            try:
                from backend.core.websocket_manager import manager as ws_manager
                await ws_manager.broadcast({
                    "type": "sla_alert",
                    "data": {
                        "intent_id": intent_id,
                        "violation_probability": best_result.violation_probability,
                        "predicted_time": best_result.predicted_time.isoformat() if best_result.predicted_time else None,
                    }
                })
            except Exception:
                pass

        return best_result

    def _try_predict_chain(self, metric_history: list[float]) -> Optional[dict]:
        result = self._prophet_predict(metric_history)
        if result is not None:
            return result

        result = self._statistical_predict(metric_history)
        if result is not None:
            return result

        result = self._rolling_avg_predict(metric_history)
        return result

    def _prophet_predict(self, metric_history: list[float], periods: int = 12) -> Optional[dict]:
        try:
            from prophet import Prophet
            import pandas as pd
        except ImportError:
            logger.debug("Prophet not available, falling back to statistical method")
            return None

        try:
            now = datetime.now(timezone.utc)
            dates = [now - timedelta(minutes=len(metric_history) - i) for i in range(len(metric_history))]
            df = pd.DataFrame({
                "ds": dates,
                "y": metric_history,
            })

            model = Prophet(
                interval_width=0.95,
                changepoint_prior_scale=0.05,
            )
            model.fit(df)

            future = model.make_future_dataframe(periods=periods, freq="min")
            forecast = model.predict(future)

            tail = forecast.tail(periods)
            predicted_values = tail["yhat"].tolist()
            lower_bound = tail["yhat_lower"].tolist()
            upper_bound = tail["yhat_upper"].tolist()

            trend_direction = "stable"
            if len(predicted_values) >= 2:
                diff = predicted_values[-1] - predicted_values[0]
                if diff > 0:
                    trend_direction = "increasing"
                elif diff < 0:
                    trend_direction = "decreasing"

            avg_ci_width = statistics.mean(
                [u - l for u, l in zip(upper_bound, lower_bound)]
            ) if upper_bound and lower_bound else 0
            data_range = max(metric_history) - min(metric_history) if len(metric_history) > 1 else 1
            confidence = max(0.0, min(1.0, 1.0 - (avg_ci_width / (data_range * 2 + 1e-9))))

            return {
                "model": "prophet",
                "forecast": {
                    "predicted_values": [round(v, 4) for v in predicted_values],
                    "lower_bound": [round(v, 4) for v in lower_bound],
                    "upper_bound": [round(v, 4) for v in upper_bound],
                },
                "trend": trend_direction,
                "confidence": round(confidence, 4),
            }
        except Exception as e:
            logger.warning(f"Prophet prediction failed: {e}")
            return None

    def _statistical_predict(self, metric_history: list[float]) -> Optional[dict]:
        if len(metric_history) < 3:
            return None

        try:
            n = len(metric_history)
            x = list(range(n))
            y = metric_history

            x_mean = statistics.mean(x)
            y_mean = statistics.mean(y)

            numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
            denominator = sum((xi - x_mean) ** 2 for xi in x)

            if denominator == 0:
                slope = 0.0
            else:
                slope = numerator / denominator

            intercept = y_mean - slope * x_mean

            residuals = [y[i] - (slope * x[i] + intercept) for i in range(n)]
            if n > 2:
                residual_std = math.sqrt(sum(r ** 2 for r in residuals) / (n - 2))
            else:
                residual_std = 0.0

            periods = settings.sla_prediction_horizon
            forecast_values = []
            for i in range(1, periods + 1):
                future_x = n + i - 1
                forecast_values.append(round(slope * future_x + intercept, 4))

            if abs(slope) < residual_std * 0.1 + 1e-9:
                trend = "stable"
            elif slope > 0:
                trend = "increasing"
            else:
                trend = "decreasing"

            data_range = max(metric_history) - min(metric_history) if len(metric_history) > 1 else 1
            if data_range == 0:
                confidence = 0.5
            else:
                r_squared = 1 - (sum(r ** 2 for r in residuals) / (sum((yi - y_mean) ** 2 for yi in y) + 1e-9))
                confidence = max(0.0, min(1.0, r_squared))

            return {
                "model": "statistical",
                "forecast": {
                    "predicted_values": forecast_values,
                    "slope": round(slope, 6),
                    "intercept": round(intercept, 4),
                    "residual_std": round(residual_std, 4),
                },
                "trend": trend,
                "confidence": round(confidence, 4),
            }
        except Exception as e:
            logger.warning(f"Statistical prediction failed: {e}")
            return None

    def _rolling_avg_predict(self, metric_history: list[float], window: int = 10) -> Optional[dict]:
        if len(metric_history) < 2:
            return None

        try:
            effective_window = min(window, len(metric_history))
            recent = metric_history[-effective_window:]

            rolling_mean = statistics.mean(recent)
            if len(recent) > 1:
                rolling_std = statistics.stdev(recent)
            else:
                rolling_std = 0.0

            periods = settings.sla_prediction_horizon
            forecast_values = [round(rolling_mean, 4)] * periods

            if len(metric_history) >= effective_window * 2:
                older = metric_history[-effective_window * 2:-effective_window]
                older_mean = statistics.mean(older)
                diff = rolling_mean - older_mean
                if abs(diff) > rolling_std * 0.5:
                    trend = "increasing" if diff > 0 else "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "stable"

            data_range = max(metric_history) - min(metric_history) if len(metric_history) > 1 else 1
            if data_range == 0:
                confidence = 0.3
            else:
                cv = rolling_std / (rolling_mean + 1e-9)
                confidence = max(0.0, min(1.0, 1.0 - cv))

            return {
                "model": "rolling_avg",
                "forecast": {
                    "predicted_values": forecast_values,
                    "rolling_mean": round(rolling_mean, 4),
                    "rolling_std": round(rolling_std, 4),
                    "upper_bound": round(rolling_mean + 2 * rolling_std, 4),
                    "lower_bound": round(rolling_mean - 2 * rolling_std, 4),
                },
                "trend": trend,
                "confidence": round(confidence, 4),
            }
        except Exception as e:
            logger.warning(f"Rolling average prediction failed: {e}")
            return None

    def _extract_metric_histories(
        self, sla_conditions: list[dict], historical_metrics: list[dict]
    ) -> dict[str, list[float]]:
        result = {}
        for condition in sla_conditions:
            metric = condition.get("metric", "")
            device = condition.get("device", "")
            key = f"{device}:{metric}"
            values = []
            for entry in historical_metrics:
                device_data = entry.get(device, {})
                if metric in device_data:
                    val = device_data[metric]
                    if isinstance(val, (int, float)):
                        values.append(float(val))
            if values:
                result[key] = values
        return result

    def _get_threshold_for_metric(self, metric_key: str, sla_conditions: list[dict]) -> Optional[float]:
        device, metric = metric_key.split(":", 1) if ":" in metric_key else ("", metric_key)
        for condition in sla_conditions:
            if condition.get("device") == device and condition.get("metric") == metric:
                return float(condition.get("value", 0))
        return None

    def _calculate_violation_probability(
        self,
        prediction: dict,
        threshold: Optional[float],
        sla_conditions: list[dict],
        metric_key: str,
    ) -> float:
        if threshold is None:
            return 0.0

        device, metric = metric_key.split(":", 1) if ":" in metric_key else ("", metric_key)
        op = ">="
        for condition in sla_conditions:
            if condition.get("device") == device and condition.get("metric") == metric:
                op = condition.get("op", ">=")
                break

        forecast_values = prediction.get("forecast", {}).get("predicted_values", [])
        if not forecast_values:
            return 0.0

        violations = 0
        for val in forecast_values:
            if self._value_violates(val, threshold, op):
                violations += 1

        base_prob = violations / len(forecast_values)

        confidence = prediction.get("confidence", 0.5)
        adjusted_prob = base_prob * (0.5 + 0.5 * confidence)

        return min(1.0, adjusted_prob)

    def _value_violates(self, value: float, threshold: float, op: str) -> bool:
        ops = {
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        fn = ops.get(op, lambda a, b: a >= b)
        return fn(value, threshold)

    def _estimate_violation_time(
        self,
        history: list[float],
        prediction: dict,
        threshold: Optional[float],
    ) -> Optional[datetime]:
        if threshold is None:
            return None

        forecast_values = prediction.get("forecast", {}).get("predicted_values", [])
        if not forecast_values:
            return None

        for i, val in enumerate(forecast_values):
            if val >= threshold:
                return datetime.now(timezone.utc) + timedelta(minutes=i + 1)

        return None

    def get_prediction(self, intent_id: int) -> Optional[PredictionResult]:
        return self._predictions.get(intent_id)

    def get_all_predictions(self) -> list[PredictionResult]:
        return list(self._predictions.values())

    def generate_alerts(self) -> list[dict]:
        alerts = []
        for intent_id, prediction in self._predictions.items():
            if prediction.predicted_violation and prediction.violation_probability >= settings.sla_alert_threshold:
                alerts.append({
                    "intent_id": intent_id,
                    "alert_type": "sla_violation_prediction",
                    "severity": "high" if prediction.violation_probability >= 0.9 else "medium",
                    "violation_probability": prediction.violation_probability,
                    "predicted_time": prediction.predicted_time.isoformat() if prediction.predicted_time else None,
                    "prediction_model": prediction.prediction_model,
                    "confidence": prediction.confidence,
                    "message": (
                        f"SLA violation predicted for intent {intent_id} "
                        f"with probability {prediction.violation_probability:.1%} "
                        f"(model: {prediction.prediction_model})"
                    ),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                })
        return sorted(alerts, key=lambda a: a["violation_probability"], reverse=True)

    async def _persist_prediction(self, prediction: PredictionResult):
        try:
            from backend.database.connection import async_session_maker
            from backend.database.models import SLAPrediction

            async with async_session_maker() as session:
                db_record = SLAPrediction(
                    intent_id=prediction.intent_id,
                    predicted_violation=prediction.predicted_violation,
                    violation_probability=prediction.violation_probability,
                    predicted_time=prediction.predicted_time,
                    prediction_model=prediction.prediction_model,
                    confidence=prediction.confidence,
                    metrics_forecast=prediction.metrics_forecast,
                )
                session.add(db_record)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist SLA prediction for intent {prediction.intent_id}: {e}")


_predictor_instance: Optional[SLAPredictor] = None


def get_sla_predictor() -> SLAPredictor:
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = SLAPredictor()
    return _predictor_instance
