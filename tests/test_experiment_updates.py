import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plot_results
import test_web_rig


class SensorBatchTests(unittest.TestCase):
    setUp = test_web_rig.WebRigTests.setUp
    tearDown = test_web_rig.WebRigTests.tearDown

    def test_force_stop_exits_batch_immediately(self):
        self.rig.tare(); self.rig.start(self.values)
        self.rig.demo = False
        self.rig.config['limits']['max_abs_sensor_force_N'] = .5
        with patch('web_rig.get_sample', side_effect=[(1,1000,110000,False), (2,1100,120000,False)]) as read:
            self.rig.drain_sensor()
        self.assertEqual(read.call_count, 1)
        self.assertEqual(self.rig.meta['samples'], 1)
        self.assertEqual(self.rig.meta['stop_reason'], 'sensor_force_limit')

    def test_continuous_backlog_yields_within_batch_budget(self):
        self.rig.tare()
        # Pretend sample handling is continuous; the bounded loop must yield.
        tick = iter(i*.01 for i in range(100))
        with patch('web_rig.time.monotonic', side_effect=lambda: next(tick)), \
             patch('web_rig.get_sample', return_value=(1,1000,100000,False)) as read, \
             patch.object(self.rig, 'handle_sample'):
            self.rig.drain_sensor()
        self.assertLess(read.call_count, 10)


class PlotSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def run_file(self, name, outcome='held', stop='duration_complete', saturated=0):
        folder = self.root/name; folder.mkdir()
        meta = {'demo':False,'status':'finished','stop_reason':stop,'outcome':outcome,
                'config':{'material':'cork','engagement_level':'on_surface','trial_id':name,
                          'geometry':{'needle_angle_deg':52.4},'motor':{'mm_per_motor_rev':None}}}
        (folder/'metadata.json').write_text(json.dumps(meta))
        fields = ['t_s','uno_elapsed_s','sensor_force_N','saturated','motor_displacement_deg','motor_rx_monotonic_s']
        with (folder/'samples.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
            for i in range(3):writer.writerow(dict(zip(fields,[i,i,-(i+1),saturated,'',''])))

    def test_outcome_filter_excludes_slipped_and_faults(self):
        self.run_file('held');self.run_file('slipped','slipped');self.run_file('fault','held','fault: USB')
        runs, skipped=plot_results.load_runs(self.root,'cork','on_surface',2,['held'])
        self.assertEqual([r['id'] for r in runs],['held'])

    def test_saturation_is_excluded(self):
        self.run_file('saturated',saturated=1)
        runs, skipped=plot_results.load_runs(self.root,None,None,2)
        self.assertFalse(runs);self.assertIn('saturation',skipped[0][1])

    def test_magnitude_and_caption_time_reference(self):
        self.run_file('one')
        runs,_=plot_results.load_runs(self.root,None,None,2)
        plot_results.prepare(runs,'host')
        self.assertEqual(runs[0]['peak'],3)
        self.assertEqual(runs[0]['mean'],2)
        table,unit=plot_results.figure(runs,self.root/'figures')
        self.assertIn('PC receive clock',plot_results.caption(table,unit,'host'))
        self.assertEqual(table.iloc[0]['outcome'],'held')
        self.assertTrue((self.root/'figures'/'figure_overview.png').exists())
