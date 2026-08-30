"""Broken reconciler that holds an exclusive payment-table lock."""

import os
import time

import psycopg  # type: ignore[import-not-found]

DSN = os.environ.get(
    "PAYMENT_DATABASE_URL",
    "postgresql://cloudtxn:cloudtxn@postgres:5432/cloudtxn",
)

while True:
    try:
        connection_context = psycopg.connect(DSN, application_name="payment-reconciler")
        with connection_context as connection, connection.cursor() as cursor:
            cursor.execute("LOCK TABLE payments IN ACCESS EXCLUSIVE MODE")
            print("PAYMENT_RECONCILER_LOCK_ACQUIRED", flush=True)
            time.sleep(3600)
    except psycopg.Error as error:
        print(f"RECONCILER_RETRY={error}", flush=True)
        time.sleep(2)
