import tempfile
import unittest
from pathlib import Path

class OnlineTests(unittest.TestCase):
    def test_tile_budget_rejects_huge_requests(self):
        from arcgis_paper_mcp.online import tile_plan
        with self.assertRaises(ValueError):
            tile_plan([-170,-70,170,70],9,64)

    def test_tiles_cover_requested_bbox(self):
        from arcgis_paper_mcp.online import tile_plan
        result=tile_plan([85,27,86,28],8,64)
        self.assertGreater(len(result['tiles']),0)
        self.assertLessEqual(len(result['tiles']),64)
        self.assertGreater(result['pixel_size_mercator_m'],0)

    def test_region_requires_real_polygon(self):
        from arcgis_paper_mcp.online import choose_region
        with self.assertRaises(ValueError):
            choose_region([{'display_name':'Point only','geojson':{'type':'Point','coordinates':[1,2]}}])

    def test_ambiguous_search_does_not_silently_pick_first(self):
        from arcgis_paper_mcp.online import choose_region
        row={'display_name':'A','geojson':{'type':'Polygon','coordinates':[]}}
        with self.assertRaises(ValueError):
            choose_region([row,{**row,'display_name':'B'}])

    def test_historical_elevation_is_not_claimed(self):
        from arcgis_paper_mcp.online import catalog
        terrain=next(x for x in catalog() if x['id']=='terrain_tiles')
        self.assertFalse(terrain['supports_year_filter'])

if __name__=='__main__': unittest.main()
