import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inventory.core import Store
from inventory.handheld import TerminalSimulator, digest
from inventory.exchange import (export_distribution, export_terminal_batch, import_batch,
                                import_receipt, publish_json, read_json, reconciliation)


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pc = Store(self.root / 'pc.db')
        self.session = self.pc.create('商品番号,名称,数量\n0001,箱,10\n0002,袋,10\n'.encode(), ['A'], 'test')
        self.package = export_distribution(self.pc, self.session['id'], self.root / 'distribution.json')
        self.terminal = TerminalSimulator(self.root / 'terminal.db', self.package, 'SIM-01')

    def tearDown(self):
        self.terminal.close()
        self.pc.close()
        self.tmp.cleanup()

    def test_file_roundtrip_zero_missing_excess_correction_and_history(self):
        for number, quantity in enumerate(('0', '12', '8', '7')):
            self.terminal.count('0001', quantity, 'A', 'counter')
            batch_path, receipt_path = self.root / f'b{number}.json', self.root / f'r{number}.json'
            export_terminal_batch(self.terminal, batch_path)
            import_batch(self.pc, batch_path, receipt_path, 'receiver')
            import_batch(self.pc, batch_path, receipt_path, 'receiver')
            import_receipt(self.terminal, batch_path, receipt_path)
            report = reconciliation(self.pc, self.session['id'])
            self.assertEqual(report['cells'][0]['quantity'], quantity)
            self.assertEqual(report['cells'][0]['status'], 'counted')
            self.assertEqual(report['cells'][1]['status'], 'missing')
            self.assertIsNone(report['cells'][1]['quantity'])
        self.assertEqual(len(report['history']), 4)
        self.assertEqual(report['summary'][0]['difference'], '-3')

    def test_lost_receipt_file_recovered_after_pc_restart(self):
        self.terminal.count('0001', '8', 'A', 'counter')
        batch = export_terminal_batch(self.terminal, self.root / 'batch.json')
        with patch('inventory.exchange.publish_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                import_batch(self.pc, self.root / 'batch.json', self.root / 'receipt.json', 'receiver')
        self.assertEqual(len(self.pc.load(self.session['id'])['records']), 1)
        self.assertEqual(self.terminal.batch(), batch)
        self.pc.close(); self.pc = Store(self.root / 'pc.db')
        import_batch(self.pc, self.root / 'batch.json', self.root / 'receipt.json', 'receiver')
        import_receipt(self.terminal, self.root / 'batch.json', self.root / 'receipt.json')
        self.assertEqual(len(self.pc.load(self.session['id'])['records']), 1)

    def test_partial_or_invalid_batch_changes_nothing(self):
        path = self.root / 'partial.json'
        path.write_text('{"schema":', encoding='utf-8')
        with self.assertRaises(ValueError):import_batch(self.pc, path, self.root / 'ack.json', 'receiver')
        self.terminal.count('0001', '8', 'A', 'counter')
        batch = self.terminal.batch()
        invalid = copy.deepcopy(batch['records'][0]); invalid.update(id='invalid', code='unknown')
        batch['records'].append(invalid)
        batch['batch_id'] = digest({k:v for k,v in batch.items() if k != 'batch_id'})
        publish_json(self.root / 'bad.json', batch)
        with self.assertRaises(ValueError):import_batch(self.pc, self.root / 'bad.json', self.root / 'ack.json', 'receiver')
        self.assertEqual(self.pc.load(self.session['id'])['records'], [])
        self.assertFalse((self.root / 'ack.json').exists())

    def test_publish_failure_keeps_existing_file_and_no_partial_output(self):
        path = self.root / 'output.json'
        publish_json(path, {'id': 'first'})
        publish_json(path, {'id': 'first'})
        with self.assertRaises(ValueError):publish_json(path, {'id': 'second'})
        self.assertEqual(read_json(path), {'id': 'first'})
        with patch('inventory.exchange.os.link', side_effect=OSError('unsupported')):
            with self.assertRaises(OSError):publish_json(self.root / 'new.json', {'id': 'new'})
        self.assertFalse((self.root / 'new.json').exists())
        self.assertEqual(list(self.root.glob('.inventory-*.tmp')), [])

    def test_duplicate_json_keys_and_oversize_are_rejected(self):
        path = self.root / 'input.json'
        for raw in ('{"schema":1,"schema":2}', '[]', '{', '{"quantity":NaN}', '{"quantity":Infinity}'):
            path.write_text(raw, encoding='utf-8')
            with self.assertRaises(ValueError):read_json(path)
        with patch('inventory.exchange.MAX_FILE_BYTES', 10):
            path.write_text('{"value":"too long"}', encoding='utf-8')
            with self.assertRaises(ValueError):read_json(path)

    def test_conflicts_are_reported_without_summing(self):
        other = TerminalSimulator(self.root / 'other.db', self.package, 'SIM-02')
        try:
            for terminal, quantity, name in ((self.terminal, '8', 'one'), (other, '12', 'two')):
                terminal.count('0001', quantity, 'A', 'counter')
                export_terminal_batch(terminal, self.root / f'{name}.json')
                import_batch(self.pc, self.root / f'{name}.json', self.root / f'{name}-ack.json', 'receiver')
            cell = reconciliation(self.pc, self.session['id'])['cells'][0]
            self.assertEqual(cell['status'], 'conflict')
            self.assertIsNone(cell['quantity'])
            self.assertEqual([r['quantity'] for r in cell['records']], ['8','12'])
        finally:other.close()

    def test_cli_distribution_receive_and_report(self):
        self.terminal.count('0001', '0', 'A', 'counter')
        export_terminal_batch(self.terminal, self.root / 'batch.json')
        base = [sys.executable, '-m', 'inventory.exchange', '--db', str(self.root / 'pc.db')]
        for args in (
            ['distribute', '--session', self.session['id'], '--output', str(self.root / 'distribution.json')],
            ['receive', '--input', str(self.root / 'batch.json'), '--receipt', str(self.root / 'receipt.json'), '--actor', 'receiver'],
            ['report', '--session', self.session['id'], '--output', str(self.root / 'report.json')],
        ):
            result = subprocess.run(base + args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(read_json(self.root / 'report.json')['cells'][0]['quantity'], '0')
        result = subprocess.run(base + ['receive', '--input', str(self.root / 'absent.json'), '--receipt', str(self.root / 'x.json'), '--actor', 'receiver'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
