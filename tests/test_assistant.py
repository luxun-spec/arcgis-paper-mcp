import json
import io
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from arcgis_paper_mcp.assistant_support import (validate_plan, request_plan,
                                             validate_endpoint, validate_job, detect_pro_python,
                                             requirement_gaps, save_settings, read_settings)
from arcgis_paper_mcp.pro_worker import handle_request, rule_plan


class DesktopTests(unittest.TestCase):
    def test_worker_returns_after_exit_without_appdata_rename(self):
        from arcgis_paper_mcp.pro_worker import main
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'response.json'
            stdin=io.TextIOWrapper(io.BytesIO(json.dumps({'operation':'plan','request':'尼泊尔地形图'}).encode()))
            with patch('sys.argv',['worker',str(path)]), patch('sys.stdin',stdin), patch('os.replace',side_effect=OSError('cross device')):
                main()
            self.assertTrue(json.loads(path.read_text(encoding='utf-8'))['ok'])

    def test_builtin_rule_handles_video_style_request_without_external_client(self):
        plan=rule_plan('帮我画一个云南省的研究区图，只用DEM')
        self.assertEqual(plan['region'],'云南省')
        self.assertEqual(plan['unmet_requirements'],[])
        self.assertEqual(rule_plan('制作尼泊尔研究区地形图')['region'],'Nepal')
        self.assertEqual(rule_plan('帮我制作青藏高原的论文研究区地形图，只用DEM')['region'],'青藏高原')
        with self.assertRaises(ValueError):rule_plan('随便帮我画一个')

    def test_rules_keep_explicit_ui_parameters_and_apply_text_style(self):
        plan=rule_plan('青藏高原灰度地形图，关闭经纬网',defaults={'zoom':6,'relief_strength':.4})
        self.assertEqual(plan['zoom'],6)
        self.assertEqual(plan['terrain_palette'],'gray')
        self.assertEqual(plan['grid_mode'],'off')
        self.assertEqual(plan['relief_strength'],.4)

    def test_worker_rejects_arbitrary_actions_and_unsupported_render(self):
        with self.assertRaises(ValueError):handle_request({'operation':'execute_python','code':'print(1)'})
        with self.assertRaises(ValueError):handle_request({'operation':'render','plan':{'region':'Nepal','unmet_requirements':['土地利用']}})

    def test_pro_discovery_accepts_official_pth_environment(self):
        with tempfile.TemporaryDirectory() as td:
            env=Path(td);python=env/'python.exe';python.touch()
            site=env/'Lib/site-packages';site.mkdir(parents=True)
            (site/'ArcGISPro.pth').write_text('import arcpy_init; arcpy_init.set_product_paths()')
            with patch.dict('os.environ',{'PAPER_MCP_ARCGIS_PYTHON':str(python)}):
                self.assertEqual(detect_pro_python(),str(python))

    def test_unsupported_requests_are_not_silently_ignored(self):
        self.assertTrue(requirement_gaps('尼泊尔2020年土地利用，30m分辨率'))
        self.assertFalse(requirement_gaps('尼泊尔论文研究区地形图，自然配色'))

    def test_settings_exclude_credentials(self):
        with tempfile.TemporaryDirectory() as td, patch('pathlib.Path.home',return_value=Path(td)):
            save_settings({'project':'seed.aprx','key':'private-secret','model':'test'})
            raw=(Path(td)/'.arcgis-paper-mcp/desktop.json').read_text()
            self.assertNotIn('private-secret',raw)
            self.assertEqual(read_settings(),{'project':'seed.aprx','model':'test'})

    def test_plan_rejects_untrusted_extra_fields_and_types(self):
        for patch in ({'command':'rm'}, {'zoom':True}, {'relief_strength':float('nan')},
                      {'terrain_palette':'neon'}, {'region':''}, {'unmet_requirements':'ignored'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_plan(dict(region='Nepal',**patch) if 'region' not in patch else patch)

    def test_plan_preserves_unmet_requirements(self):
        plan=validate_plan({'region':'尼泊尔','unmet_requirements':['2020年土地利用']})
        self.assertEqual(plan['unmet_requirements'],['2020年土地利用'])
        self.assertEqual(plan['terrain_palette'],'natural')

    def test_model_endpoint_never_sends_key_over_public_plain_http(self):
        for url in ('http://example.com/v1', 'https://user:secret@example.com/v1', 'file:///tmp/a',
                    'https://example.com/v1?api_key=secret'):
            with self.assertRaises(ValueError): validate_endpoint(url)
        self.assertEqual(validate_endpoint('http://127.0.0.1:8080/v1'),
                         'http://127.0.0.1:8080/v1/chat/completions')

    def test_model_protocol_and_no_secret_in_errors(self):
        observed={}
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                observed['path']=self.path
                observed['payload']=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                observed['auth']=self.headers.get('Authorization')
                data=json.dumps({'choices':[{'message':{'content':json.dumps({'region':'Nepal','zoom':7})}}]}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(data)
            def log_message(self,*args): pass
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            plan=request_plan('画尼泊尔地形图',f'http://127.0.0.1:{server.server_port}/v1','local','test-private-key')
            self.assertEqual(plan['region'],'Nepal')
            self.assertEqual(observed['path'],'/v1/chat/completions')
            self.assertEqual(observed['auth'],'Bearer test-private-key')
            self.assertIn('画尼泊尔地形图',observed['payload']['messages'][-1]['content'])
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_job_refuses_missing_seed_and_nonempty_output(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); seed=base/'seed.aprx'; python=base/'python.exe'
            python.touch();seed.touch()
            with self.assertRaises(ValueError): validate_job(str(python),str(base/'missing.aprx'),str(base/'new'))
            (base/'used').mkdir();(base/'used'/'research.txt').touch()
            with self.assertRaises(ValueError):validate_job(str(python),str(seed),str(base/'used'))
            validate_job(str(python),str(seed),str(base/'new'))


if __name__=='__main__': unittest.main()
