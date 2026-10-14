"""Retire previous local banks only after checking the replacement is complete."""
import json

from api.bank_lifecycle import retain_curated_bank
from api.database import get_connection


def main():
    with get_connection() as conn:
        if conn.info.host not in ('localhost','127.0.0.1','::1',''):
            raise SystemExit('This command only changes the local database.')
        conn.execute("SET LOCAL lock_timeout='10s'")
        release=conn.execute('''SELECT r.release_id FROM penalty_bank_releases r
            JOIN trivia_bank_validation_runs v ON v.run_id=r.validation_run_id
            JOIN trivia_bank_batches b USING(batch_id) WHERE b.source_name='curated-pl-3000-v1'
            ORDER BY r.created_at DESC LIMIT 1''').fetchone()
        if not release:raise SystemExit('Publish and audit the new bank first. Nothing changed.')
        report=retain_curated_bank(conn,release['release_id'],'local-bank-replacement')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
