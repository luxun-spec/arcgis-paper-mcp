import json
import tempfile
import time
import unittest
from pathlib import Path


class ConfigTests(unittest.TestCase):
    def config(self, **kwargs):
        from arcgis_paper_mcp.config import normalize
        return normalize({'boundary': 'data/area.shp', 'output_dir': 'result', **kwargs}, Path.cwd())

    def test_relative_paths_are_anchored_to_config_folder(self):
        cfg = self.config()
        self.assertEqual(cfg['boundary'], str(Path('data/area.shp').resolve()))
        self.assertEqual(cfg['dpi'], 300)

    def test_rejects_invalid_template_dpi_and_crs(self):
        for kw in ({'template': 'bad'}, {'dpi': 0}, {'detail_crs': 0}, {'dpi': True}, {'extra': 'typo'}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.config(**kw)

    def test_no_overwrite_or_missing_boundary(self):
        from arcgis_paper_mcp.config import normalize
        with self.assertRaises(ValueError):
            normalize({'output_dir': 'foo'}, Path.cwd())
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'result'
            p.mkdir()
            (p / 'existing.txt').write_text('research')
            with self.assertRaises(FileExistsError):
                normalize({'boundary': 'area.shp', 'output_dir': str(p)}, Path(tmp))

    def test_templates_fit_page_and_do_not_overlap(self):
        from arcgis_paper_mcp.config import frames
        for template in ('study_area', 'watershed'):
            rects = list(frames(template).values())
            for x, y, w, h in rects:
                self.assertTrue(0 <= x < x+w <= 297)
                self.assertTrue(0 <= y < y+h <= 210)
            for i, (x,y,w,h) in enumerate(rects):
                for a,b,c,d in rects[i+1:]:
                    self.assertFalse(x<a+c and a<x+w and y<b+d and b<y+h)

    def test_hydrology_threshold_and_license_are_explicit(self):
        from arcgis_paper_mcp.config import hydrology_config
        for value in (0, -1, float('nan'), True):
            with self.assertRaises(ValueError):
                hydrology_config({'dem': 'dem.tif', 'output_dir': 'out', 'threshold_km2': value}, Path.cwd())


class QueueTests(unittest.TestCase):
    def test_expired_request_does_not_execute(self):
        from arcgis_paper_mcp.transport import atomic_json, process_one
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            atomic_json(q / 'a.request.json', {'id': 'a', 'deadline': time.time()-1, 'operation': 'ping', 'params': {}})
            calls = []
            process_one(q, lambda op, params: calls.append(op))
            result = json.loads((q/'a.response.json').read_text())
            self.assertFalse(result['ok'])
            self.assertEqual(calls, [])

    def test_queue_roundtrip_and_unknown_operation(self):
        from arcgis_paper_mcp.transport import atomic_json, process_one
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            for identifier, op in [('a','ping'), ('b','execute_python')]:
                atomic_json(q/f'{identifier}.request.json', {'id':identifier, 'deadline':time.time()+10, 'operation':op, 'params':{}})
            process_one(q, lambda op, params: {'version':'3.6'})
            self.assertEqual(json.loads((q/'a.response.json').read_text())['result']['version'], '3.6')
            process_one(q, lambda *args: self.fail('arbitrary operation dispatched'))
            self.assertFalse(json.loads((q/'b.response.json').read_text())['ok'])

    def test_queue_does_not_trust_request_id_as_path(self):
        from arcgis_paper_mcp.transport import atomic_json, process_one
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            atomic_json(q/'a.request.json', {'id':'../escape', 'deadline':time.time()+10, 'operation':'ping', 'params':{}})
            process_one(q, lambda *args: self.fail('invalid id dispatched'))
            self.assertFalse(json.loads((q/'a.response.json').read_text())['ok'])


if __name__ == '__main__':
    unittest.main()
