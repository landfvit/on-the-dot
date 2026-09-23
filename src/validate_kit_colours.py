"""Run the 100 named kit checks and export their actual outcomes, without DB writes."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class Results(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.records=[]

    def startTest(self,test):
        self.started=time.monotonic();super().startTest(test)

    def record(self,test,status,details=None):
        self.records.append({'id':test.id(),'description':test.shortDescription(),'status':status,
            'duration_ms':round((time.monotonic()-self.started)*1000,3),'details':details})

    def addSuccess(self,test):
        super().addSuccess(test);self.record(test,'passed')

    def addFailure(self,test,err):
        super().addFailure(test,err);self.record(test,'failed',self._exc_info_to_string(err,test))

    def addError(self,test,err):
        super().addError(test,err);self.record(test,'error',self._exc_info_to_string(err,test))

    def addSkip(self,test,reason):
        super().addSkip(test,reason);self.record(test,'skipped',reason)


def main():
    report_path=ROOT/'reports/kits/pl_kit_colours.json'
    report=json.loads(report_path.read_text())
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_kit_validation_100.py')
    if suite.countTestCases()!=100:raise ValueError('Expected exactly 100 named validation cases')
    result=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(suite)
    summary={'created_at':datetime.now(timezone.utc).isoformat(),'tests_run':result.testsRun,
        'outcomes':dict(Counter(r['status'] for r in result.records)),
        'source_report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
        'coverage_at_validation':report['summary'],
        'scope':'Engineering validation, not independent historical kit/product verification.'}
    output=ROOT/'reports/kits'
    (output/'validation_100.json').write_text(json.dumps({'summary':summary,'cases':result.records},indent=2)+'\n')
    lines=['# Kit Validation: 100 Cases','',f'Run: {summary["created_at"]}',
        f'Outcomes: {summary["outcomes"]}','',summary['scope'],'',
        '28 seasonal integrity checks, 13 solid-colour checks, 12 combinations, 8 pixel boundary cases, '
        '24 answer-grading cases, 10 invalid specifications and 5 import safety checks.',
        'Missing source images remain missing. Passing these checks does not verify their colours.',
        f'Source report SHA-256: `{summary["source_report_sha256"]}`','',
        '| Case | Check | Result |','| --- | --- | --- |']
    for number,row in enumerate(result.records,1):
        lines.append(f'| {number} | {row["description"]} | {row["status"]} |')
    for row in result.records:
        if row['details']:lines.extend(['',f'## {row["id"]}','','```text',row['details'],'```'])
    (output/'validation_100.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2))
    return 0 if result.wasSuccessful() and result.testsRun==100 and not result.skipped else 1


if __name__=='__main__':sys.exit(main())
