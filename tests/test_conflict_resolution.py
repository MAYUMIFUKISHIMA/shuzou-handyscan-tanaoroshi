import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from inventory.core import Store
from inventory.exchange import reconciliation, resolve_conflict, publish_json
from inventory.handheld import TerminalSimulator, distribution, receive_batch


class ConflictResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pc = Store(self.root / 'pc.db')
        self.s = self.pc.create('商品番号,名称,数量\n0001,箱,10\n'.encode(), ['A'], 'test')
        for device, quantity in (('one','8'), ('two','12')):
            terminal = TerminalSimulator(self.root / f'{device}.db', distribution(self.s), device)
            try:
                terminal.count('0001', quantity, 'A', device)
                receive_batch(self.pc, terminal.batch(), 'receiver')
            finally:terminal.close()
        report = reconciliation(self.pc, self.s['id'])
        self.proposal = dict(session_id=self.s['id'], revision=report['revision'], code='0001',
                             location='A', quantity='7', reason='棚位置Aで再計数した',
                             supersedes=[r['id'] for r in report['cells'][0]['records']])

    def tearDown(self):
        self.pc.close(); self.tmp.cleanup()

    def test_resolution_replaces_candidates_preserves_history_and_retry(self):
        result = resolve_conflict(self.pc, self.proposal, 'reviewer', 'resolve-001')
        self.pc.close(); self.pc = Store(self.root / 'pc.db')
        self.assertEqual(resolve_conflict(self.pc, self.proposal, 'reviewer', 'resolve-001'), result)
        report = reconciliation(self.pc, self.s['id'])
        self.assertEqual(report['cells'][0]['status'], 'counted')
        self.assertEqual(report['cells'][0]['quantity'], '7')
        self.assertEqual([r['quantity'] for r in report['history']], ['8','12','7'])
        event = report['audit'][-1]
        self.assertEqual(event['action'], 'resolve_conflict')
        self.assertEqual(event['reason'], self.proposal['reason'])
        self.assertEqual(event['actor'], 'reviewer')
        self.assertEqual(event['supersedes'], self.proposal['supersedes'])

    def test_invalid_or_stale_resolution_changes_nothing(self):
        before = self.pc.load(self.s['id'])
        for changes in ({'reason':''}, {'quantity':'-1'}, {'supersedes':self.proposal['supersedes'][:1]},
                        {'revision':0}, {'supersedes':[{}]}):
            proposal = dict(self.proposal, **changes)
            with self.assertRaises(ValueError):resolve_conflict(self.pc, proposal, 'reviewer', 'attempt')
            self.assertEqual(self.pc.load(self.s['id']), before)

    def test_reused_operation_id_different_quantity_is_rejected(self):
        resolve_conflict(self.pc, self.proposal, 'reviewer', 'same-id')
        changed = copy.deepcopy(self.proposal); changed['quantity'] = '0'
        with self.assertRaises(ValueError):resolve_conflict(self.pc, changed, 'reviewer', 'same-id')
        self.assertEqual(reconciliation(self.pc, self.s['id'])['cells'][0]['quantity'], '7')

    def test_cannot_resolve_non_conflict_or_modify_finalized_inventory(self):
        resolve_conflict(self.pc, self.proposal, 'reviewer', 'resolution')
        session = self.pc.load(self.s['id'])
        proposal = dict(self.proposal, revision=session['revision'], supersedes=['resolution'])
        with self.assertRaises(ValueError):resolve_conflict(self.pc, proposal, 'reviewer', 'again')
        session = self.pc.change(session['id'], session['revision'], 'complete', 'reviewer', {'location':'A'})
        session = self.pc.change(session['id'], session['revision'], 'finalize', 'reviewer', None)
        with self.assertRaises(ValueError):
            resolve_conflict(self.pc, dict(proposal,revision=session['revision']), 'reviewer', 'finalized')

    def test_cli_resolves_zero_and_retries_same_operation(self):
        proposal = dict(self.proposal, quantity='0')
        source = self.root / 'resolution.json'
        publish_json(source, proposal)
        command = [sys.executable, '-m', 'inventory.exchange', '--db', str(self.root/'pc.db'),
                   'resolve-conflict', '--input', str(source), '--actor', 'reviewer', '--request-id', 'cli-resolution']
        for _ in range(2):
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        report = reconciliation(self.pc, self.s['id'])
        self.assertEqual(report['cells'][0]['quantity'], '0')
        self.assertEqual(len(report['history']), 3)
