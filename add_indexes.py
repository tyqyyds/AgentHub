#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add missing indexes to SQLite database for performance optimization."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "backend", "data", "netops.db")

INDEXES = [
    # Intent table indexes
    "CREATE INDEX IF NOT EXISTS ix_intents_approval_status ON intents(approval_status)",
    "CREATE INDEX IF NOT EXISTS ix_intents_execution_status ON intents(execution_status)",
    "CREATE INDEX IF NOT EXISTS ix_intents_sla_status ON intents(sla_status)",
    "CREATE INDEX IF NOT EXISTS ix_intents_created_at ON intents(created_at)",
    "CREATE INDEX IF NOT EXISTS ix_intents_intent_name ON intents(intent_name)",
    # AuditLog table indexes
    "CREATE INDEX IF NOT EXISTS ix_audit_user_id ON audit_logs(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action)",
    "CREATE INDEX IF NOT EXISTS ix_audit_status ON audit_logs(status)",
    "CREATE INDEX IF NOT EXISTS ix_audit_security_type ON audit_logs(security_type)",
    "CREATE INDEX IF NOT EXISTS ix_audit_timestamp ON audit_logs(timestamp)",
    # SelfHealingEvent indexes
    "CREATE INDEX IF NOT EXISTS ix_she_status ON self_healing_events(status)",
    "CREATE INDEX IF NOT EXISTS ix_she_severity ON self_healing_events(severity)",
    # WorkOrder indexes
    "CREATE INDEX IF NOT EXISTS ix_wo_status ON work_orders(status)",
    "CREATE INDEX IF NOT EXISTS ix_wo_created_by ON work_orders(created_by)",
]

def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Adding indexes to database...")
    for sql in INDEXES:
        try:
            cursor.execute(sql)
            idx_name = sql.split("ix_")[1].split(" ")[0] if "ix_" in sql else "?"
            print(f"  OK: {idx_name}")
        except Exception as e:
            print(f"  FAIL: {e}")

    conn.commit()

    # Verify indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix_%'")
    indexes = cursor.fetchall()
    print(f"\nTotal custom indexes: {len(indexes)}")
    for idx in indexes:
        print(f"  {idx[0]}")

    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
