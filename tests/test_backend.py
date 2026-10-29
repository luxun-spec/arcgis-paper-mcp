import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS


class BackendTests(unittest.TestCase):
    def test_mercator_relief_spacing_uses_local_ground_scale(self):
        from arcgis_paper_mcp.backend import mercator_ground_factor
        self.assertAlmostEqual(mercator_ground_factor(0),1)
        self.assertAlmostEqual(mercator_ground_factor(60),.5)
    def test_scale_units_use_native_unit_identifier(self):
        import json
        from arcgis_paper_mcp.backend import configure_scale
        cim = NS(labelSymbol=NS(symbol=NS()),unitLabelSymbol=NS(symbol=NS()),numberFormat=NS())
        bar = NS(getDefinition=lambda _:cim,setDefinition=lambda value:None)
        configure_scale(bar,NS(camera=NS(scale=2_000_000)))
        self.assertEqual(cim.units,{'uwkid':9036})
        self.assertGreater(cim.division,0)
        self.assertLess(cim.division*cim.divisions,100)

    def test_named_user_license_does_not_use_concurrent_checkout(self):
        from arcgis_paper_mcp.backend import spatial_license
        api = NS(GetInstallInfo=lambda:{'LicenseType':'NamedUser'},
                 CheckExtension=lambda _:'Available',
                 CheckOutExtension=lambda _:self.fail('not a concurrent license'),
                 CheckInExtension=lambda _:self.fail('not a concurrent license'))
        with spatial_license(api):
            pass

    def test_concurrent_license_is_returned_after_failure(self):
        from arcgis_paper_mcp.backend import spatial_license
        calls = []
        api = NS(GetInstallInfo=lambda:{'LicenseType':'ConcurrentUse'},
                 CheckExtension=lambda _:'Available',
                 CheckOutExtension=lambda _:calls.append('out') or 'CheckedOut',
                 CheckInExtension=lambda _:calls.append('in'))
        with self.assertRaises(RuntimeError):
            with spatial_license(api):
                raise RuntimeError('tool failed')
        self.assertEqual(calls,['out','in'])

    def test_existing_raster_statistics_are_reused(self):
        from arcgis_paper_mcp.backend import ensure_statistics
        api = NS(Raster=lambda _:NS(minimum=0,maximum=2000),
                 management=NS(CalculateStatistics=lambda _:self.fail('unnecessary raster scan')))
        ensure_statistics(api,'dem.tif')

    def test_output_claim_is_exclusive_and_does_not_overwrite(self):
        from arcgis_paper_mcp.backend import claim_output
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'new'
            claim_output(out)
            with self.assertRaises(FileExistsError):
                claim_output(out)

    def test_polygon_styling_uses_geometry_not_unsupported_symbol_type(self):
        from arcgis_paper_mcp.backend import _vector
        symbol = NS()
        sym = NS(renderer=NS(symbol=symbol),updateRenderer=lambda _:None)
        layer = NS(symbology=sym,isFeatureLayer=True)
        m = NS(addDataFromPath=lambda _:layer)
        _vector(m,'area.shp','Boundary',color=[1,2,3,100],width=1)
        self.assertEqual(symbol.outlineWidth,1)
        self.assertEqual(symbol.color,{'RGB':[255,255,255,0]})

    def test_undefined_crs_is_rejected_before_rendering(self):
        from arcgis_paper_mcp.backend import describe
        api = NS(Exists=lambda p: True, Describe=lambda p: NS(spatialReference=NS(name='Unknown', type='Unknown')))
        with self.assertRaisesRegex(ValueError, 'coordinate system'):
            describe(api, 'unknown.shp')

    def test_hydrology_refuses_degree_and_foot_dem(self):
        from arcgis_paper_mcp.backend import metric_cell_area
        for kind, unit in [('Geographic','Degree'),('Projected','Foot')]:
            desc = NS(spatialReference=NS(type=kind, linearUnitName=unit),meanCellWidth=30,meanCellHeight=30)
            with self.assertRaises(ValueError):
                metric_cell_area(desc)

    def test_area_threshold_uses_real_cell_area(self):
        from arcgis_paper_mcp.backend import threshold_cells
        desc = NS(spatialReference=NS(type='Projected',linearUnitName='Meter'),meanCellWidth=100,meanCellHeight=50)
        self.assertEqual(threshold_cells(desc, 2), 400)

    def test_dispatch_does_not_accept_arbitrary_python(self):
        from arcgis_paper_mcp.backend import dispatch
        with self.assertRaisesRegex(ValueError, 'allowed'):
            dispatch('execute_python', {'code':'anything'})

    def test_missing_data_rejected(self):
        from arcgis_paper_mcp.backend import describe
        with self.assertRaises(FileNotFoundError):
            describe(NS(Exists=lambda _:False),'missing.tif')


if __name__ == '__main__':
    unittest.main()
