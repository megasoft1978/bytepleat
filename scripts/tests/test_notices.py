"""Cargo target graph and rustc provenance parsing regression tests."""
from __future__ import annotations
import sys, unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collect_notices

class NoticeCollectorTests(unittest.TestCase):
    def test_release_graph_keeps_normal_and_build_edges_but_excludes_dev_edges(self):
        nodes={
            "root":{"deps":[
                {"pkg":"runtime","dep_kinds":[{"kind":None,"target":None}]},
                {"pkg":"generator","dep_kinds":[{"kind":"build","target":None}]},
                {"pkg":"test-only","dep_kinds":[{"kind":"dev","target":None}]},
                {"pkg":"runtime","dep_kinds":[{"kind":None,"target":None},{"kind":"dev","target":None}]},
            ]},
            "runtime":{"deps":[]},"generator":{"deps":[]},"test-only":{"deps":[]}}
        self.assertEqual(collect_notices.release_reachable(nodes,"root"),{"root","runtime","generator"})

    def test_parses_rustc_commit_hash_colon_format(self):
        self.assertEqual(collect_notices.rust_commit_hash("rustc 1.93.0 (abc123 2026-01-01)\ncommit-hash: abc123def\n"),"abc123def")
        self.assertIsNone(collect_notices.rust_commit_hash("rustc 1.93.0\n"))

if __name__=="__main__":unittest.main()
