"""Offline integrity and execution-accounting verification; no model or Docker calls."""
import collections
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def digest(value):
    return hashlib.sha256(value).hexdigest()


def main():
    expected = json.loads((HERE / 'raw-manifest.json').read_text())
    assert digest((HERE / 'raw-results.zip').read_bytes()) == expected['archive_sha256']
    metrics = json.loads((HERE / 'metrics.json').read_text())
    decisions = json.loads((HERE / 'adjudications.json').read_text())['records']
    with zipfile.ZipFile(HERE / 'raw-results.zip') as archive:
        assert set(archive.namelist()) == set(expected['files'])
        for name, hashed in expected['files'].items():
            assert digest(archive.read(name)) == hashed, name

        def read(name):
            return json.loads(archive.read(name))

        results = read('results.json')
        manifest = read('manifest.json')
        records = results['records']
        assert len(records) == len(decisions) == metrics['records'] == 13
        assert len({r['finding_id'] for r in records}) == 13
        for name in ['results.json', 'manifest.json', 'audit-diagnostics.json', 'audit-source-excerpts.json']:
            assert (HERE / name).read_bytes() == archive.read(name), name
        assert {r['finding_id'] for r in records} == {r['finding_id'] for r in manifest['input_records']}
        primary = 0
        for record, decision in zip(records, decisions):
            assert record['finding_id'] == decision['finding_id']
            prefix = record['output'] + '/'
            test = archive.read(prefix + 'test_reproduction.py')
            finding = read(prefix + 'original-evidence.json')['finding']
            assert test == finding['reproduction']['plan']['test_code'].encode()
            assert digest(test) == record['test_sha256']
            assert record['snapshot_sha256'] == finding['reproduction']['execution_snapshot_sha256']
            assert len(record['trials']) == 4
            assert {(t['implementation'], t['repetition']) for t in record['trials']} == {
                ('old', 1), ('new', 1), ('old', 2), ('new', 2)}
            for trial in record['trials']:
                filename = prefix + f"{trial['implementation']}-{trial['repetition']}"
                attempt = read(filename + '.json')
                assert digest(archive.read(filename + '.log')) == attempt['log_sha256']
                assert attempt['log'].encode() == archive.read(filename + '.log')
                execution = attempt['execution']
                assert execution['tests_run'] == trial['tests_run'] == 1
                assert [o['exception_type'] for o in execution['observations']] == trial['failure_types']
                assert [o.get('message') for o in execution['observations']] == trial['messages']
                assert attempt['image_id'] == trial['image_id'] == finding['reproduction']['attempts'][0]['image_id']
                primary += 1
            for implementation in ['old', 'new']:
                trials = [t for t in record['trials'] if t['implementation'] == implementation]
                assert all((t['old_gate'], t['new_gate'], t['failure_types'], t['messages']) ==
                           (trials[0]['old_gate'], trials[0]['new_gate'], trials[0]['failure_types'], trials[0]['messages']) for t in trials)
                accepted = all(t[implementation + '_gate'] == 'failure_observed' for t in trials)
                assert accepted == record[implementation + '_execution_gate_pass'] == decision[implementation + '_gate_pass']
            counterpart = read(prefix + 'counterpart.json')
            assert digest(archive.read(prefix + 'counterpart.log')) == counterpart['log_sha256']
            assert counterpart['execution']['tests_run'] == 1
            assert [o['exception_type'] for o in counterpart['execution']['observations']] == record['counterpart']['failure_types']
        for relative, hashed in manifest['source_sha256'].items():
            name = 'audit-support/' + ('baseline/' if relative.startswith('outputs/') else 'src/') + Path(relative).name
            assert digest(archive.read(name)) == hashed, relative
        assert primary == metrics['primary_containers'] == results['primary_containers'] == 52
        assert results['counterpart_containers'] == metrics['opposite_snapshot_containers'] == 13
        diagnostics = read('audit-diagnostics.json')
        assert diagnostics['containers'] == metrics['supplemental_evaluator_containers'] == 2
        assert digest(archive.read('audit-caller-test.py')) == diagnostics['test_sha256']
        for diagnostic in diagnostics['records']:
            attempt = read('audit-caller-' + diagnostic['side'] + '.json')
            assert attempt['execution']['tests_run'] == 1
            assert [o['exception_type'] for o in attempt['execution']['observations']] == diagnostic['exceptions'] == ['IndexError']
        assert metrics['total_containers'] == primary + len(records) + diagnostics['containers'] == 67
        assert metrics['old_execution_gate_accepted'] == sum(r['old_execution_gate_pass'] for r in records) == 13
        assert metrics['new_execution_gate_accepted'] == sum(r['new_execution_gate_pass'] for r in records) == 12
        assert metrics['semantic_categories'] == dict(collections.Counter(d['category'] for d in decisions))
        assert metrics['reference_confirmed_records'] == sum(d['basis'] == 'reference_contract_and_control' for d in decisions) == 1
        assert metrics['additional_source_supported_records_pending_human_review'] == sum(d['basis'] == 'source_consistency_inference' for d in decisions) == 6
        assert results['api_calls'] == manifest['api_calls'] == diagnostics['api_calls'] == metrics['deepseek_api_calls'] == 0
        assert results['source_frozen'] and metrics['implementation_frozen']
        assert not any(d['human_verified'] for d in decisions)
    print('PASS: 218 archived files, 13 unchanged Agent tests, 52 paired executions, 13 opposite-version controls, 2 evaluator diagnostics; 0 provider calls.')


if __name__ == '__main__':
    main()
