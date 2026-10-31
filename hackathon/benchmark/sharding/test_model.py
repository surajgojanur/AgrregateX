import unittest
from model import Order, ShardUnavailable, ServiceUnavailable, compare_shards, multiset_mismatches, oracle_streams, route, validate_mapping

class ShardingContractTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {1: "a", 2: "a", 3: "b", 4: "b"}
        self.rows = [Order(1, 1, "2026-10-31", "2026-10-31T10", 7, 2, "paid", 2, 350),
                     Order(1, 2, "2026-10-31", "2026-10-31T10", 7, 2, "paid", 1, 350),
                     Order(2, 3, "2026-11-01", "2026-11-01T00", None, None, "cancelled", 1, 999),
                     Order(3, 4, "2026-10-31", "2026-10-31T23", 9, 4, "shipped", 3, 100)]
    def test_directory_is_complete_and_zero_order_tenant_is_allowed(self):
        validate_mapping(self.mapping, ["a", "b"], [1, 2, 3, 4])
        out = compare_shards(self.mapping, {"a": self.rows[:3], "b": self.rows[3:]}, [1,2,3,4], ["a","b"])
        self.assertEqual(out["b"]["st_day_product_status"][(3,"2026-10-31",9,"shipped")], (1,3,300))
        empty = compare_shards({1:"a",2:"b"}, {"a":[self.rows[0]],"b":[]}, [1,2], ["a","b"])
        self.assertEqual(empty["b"]["st_day_product_status"], {})
    def test_mapping_rejects_missing_and_unknown_shards(self):
        with self.assertRaises(AssertionError): validate_mapping({1:"a"},["a","b"],[1,2])
        with self.assertRaises(AssertionError): validate_mapping({1:"x",2:"b"},["a","b"],[1,2])
    def test_three_stream_grains_and_nullable_keys(self):
        out = oracle_streams(self.rows)
        self.assertEqual(set(out), {"st_day_product_status","st_day_category_status","st_hour_category_status"})
        self.assertEqual(out["st_day_product_status"][(1,"2026-10-31",7,"paid")], (2,3,1050))
        self.assertEqual(out["st_day_category_status"][(2,"2026-11-01",None,"cancelled")], (1,1,999))
        self.assertEqual(out["st_hour_category_status"][(3,"2026-10-31T23",4,"shipped")], (1,3,300))
    def test_multiset_comparison_finds_missing_and_extra_independently(self):
        expected={"k":(2,3,4),"x":(1,1,1)}; actual={"k":(2,3,4),"y":(9,9,9)}
        missing,extra=multiset_mismatches(expected,actual)
        self.assertEqual(missing,{"x":(1,1,1)})
        self.assertEqual(extra,{"y":(9,9,9)})
    def test_duplicate_or_misplaced_tenant_fails(self):
        with self.assertRaises(AssertionError): compare_shards(self.mapping,{"a":self.rows[:3],"b":self.rows[2:]},[1,2,3,4],["a","b"])
        with self.assertRaises(AssertionError): compare_shards(self.mapping,{"a":self.rows[:2],"b":self.rows[2:]},[1,2,3,4],["a","b"])
    def test_unavailable_returns_503_and_other_shard_read_write_work(self):
        def down(_): raise ShardUnavailable()
        clients={"a":down,"b":lambda tenant, op="read":{"tenant":tenant,"op":op}}
        with self.assertRaises(ServiceUnavailable) as err: route(1,self.mapping,clients)
        self.assertEqual(err.exception.status_code,503)
        self.assertEqual(route(3,self.mapping,clients),{"tenant":3,"op":"read"})
        self.assertEqual(route(3,self.mapping,{"a":down,"b":lambda t:{"write":t}}),{"write":3})

if __name__ == "__main__": unittest.main()
