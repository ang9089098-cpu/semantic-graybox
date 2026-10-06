# -*- coding: utf-8 -*-
"""
Clustering Semantics Test Matrix (GPU-free)
============================================

의도한 규칙을 코드로 명세한다:

    같은 semantic role + 동등한 guide 크기(proportion/size signature)
    → 같은 geometry master

    anchor 위치나 방향 접미사(FL/FR/BL/BR)는 geometry master 정체성을
    결정해서는 안 된다. 이들은 placement/slot 메타데이터로 남아야 한다.

이 테스트는 `semantic_graybox_extractor.cluster_parts` / `evaluate_cluster_constraints`
를 bpy 없이 순수 dict 로 직접 호출한다(실제 extractor 파이프라인 함수를 그대로 사용,
로직을 재구현하지 않음).

기존 tolerance 메커니즘(compare_dimensions, DIMENSION_TOLERANCE) 을 그대로 사용한다.
임의의 새 tolerance 를 만들지 않는다.

실행:
    python -m unittest tests.test_clustering_semantics -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import semantic_graybox_extractor as ext


def make_part(name, dims, direction_suffix=""):
    """cluster_parts 가 기대하는 최소 파트 dict. (extractor.extract_part 형태와 호환)"""
    group_key, _ = ext.extract_group_key(name)
    return {
        "name": name,
        "parent": None,
        "group_key": group_key,
        "suffix": direction_suffix,
        "direction": ext.parse_direction_suffix(direction_suffix),
        "transform": {"location": [0.0, 0.0, 0.0], "rotation_euler": [0.0, 0.0, 0.0],
                      "scale": [1.0, 1.0, 1.0]},
        "anchor_points": {
            "origin_world": [0.0, 0.0, 0.0],
            "bbox_center_world": [0.0, 0.0, 0.0],
            "dimensions": list(dims),
            "bbox_bounds_world": {"min": [0, 0, 0], "max": list(dims)},
        },
    }


def master_membership(clusters):
    """cluster_parts() 결과에서 {master_id: sorted([member names])} 만 뽑아낸다."""
    return {
        m["master_id"]: sorted(s["name"] for s in m["slots"])
        for m in clusters["master_parts"]
    }


class TestClusteringSemanticsMatrix(unittest.TestCase):
    """
    각 CASE 는 PHASE 2 명세와 1:1 대응한다. setUp 시점의 unmodified 동작에서는
    일부 케이스가 실패할 것으로 예상된다(PHASE 3 에서 실패를 기록하는 것이 목적).
    """

    SAME = (0.08, 0.08, 0.70)
    DIFF = (0.12, 0.12, 1.00)   # SAME 과 볼륨 편차가 충분히 커서(>15%) 분기를 유발해야 함

    def test_case1_same_role_same_dims_one_master(self):
        """CASE 1: 4 legs, 같은 role, 같은 dims → 1 master, 4 members."""
        parts = [make_part("Leg_01", self.SAME), make_part("Leg_02", self.SAME),
                 make_part("Leg_03", self.SAME), make_part("Leg_04", self.SAME)]
        clusters = ext.cluster_parts(parts)
        self.assertEqual(len(clusters["master_parts"]), 1,
                         "동일 크기 4개는 master 1개여야 함")
        self.assertEqual(clusters["master_parts"][0]["instance_count"], 4)

    def test_case2_three_identical_one_outlier_3_1_split(self):
        """CASE 2: 3 identical + 1 clearly different → 2 masters, 3+1 members."""
        parts = [make_part("Leg_01", self.SAME), make_part("Leg_02", self.SAME),
                 make_part("Leg_03", self.SAME), make_part("Leg_04", self.DIFF)]
        clusters = ext.cluster_parts(parts)
        counts = sorted(m["instance_count"] for m in clusters["master_parts"])
        self.assertEqual(len(clusters["master_parts"]), 2, "2개 master 여야 함")
        self.assertEqual(counts, [1, 3], "member 수는 3+1 이어야 함 (2+2 아님)")

    def test_case3_two_plus_two_distinct_sizes(self):
        """CASE 3: 2 size-A + 2 size-B → 2 masters, 2+2 members."""
        size_a = (0.08, 0.08, 0.70)
        size_b = (0.12, 0.12, 1.00)
        parts = [make_part("Leg_01", size_a), make_part("Leg_02", size_a),
                 make_part("Leg_03", size_b), make_part("Leg_04", size_b)]
        clusters = ext.cluster_parts(parts)
        counts = sorted(m["instance_count"] for m in clusters["master_parts"])
        self.assertEqual(len(clusters["master_parts"]), 2)
        self.assertEqual(counts, [2, 2])

    def test_case4_five_legs_four_identical_one_outlier(self):
        """CASE 4: 5 legs, 4 identical + 1 outlier → 2 masters, 4+1 members."""
        parts = [make_part("Leg_0{0}".format(i), self.SAME) for i in range(1, 5)]
        parts.append(make_part("Leg_05", self.DIFF))
        clusters = ext.cluster_parts(parts)
        counts = sorted(m["instance_count"] for m in clusters["master_parts"])
        self.assertEqual(len(clusters["master_parts"]), 2)
        self.assertEqual(counts, [1, 4], "member 수는 4+1 이어야 함")

    def test_case5_direction_suffix_same_dims_one_master(self):
        """CASE 5: FL/FR/BL/BR 이름, 모두 같은 dims → 1 geometry master, 4 slots."""
        parts = [
            make_part("Leg_FL", self.SAME, "fl"),
            make_part("Leg_FR", self.SAME, "fr"),
            make_part("Leg_BL", self.SAME, "bl"),
            make_part("Leg_BR", self.SAME, "br"),
        ]
        clusters = ext.cluster_parts(parts)
        self.assertEqual(len(clusters["master_parts"]), 1,
                         "방향 접미사만 다르고 크기가 같으면 geometry master 는 1개여야 함"
                         "(방향은 slot/placement 메타데이터로만 남아야 함)")
        self.assertEqual(clusters["master_parts"][0]["instance_count"], 4)
        member_names = master_membership(clusters)[clusters["master_parts"][0]["master_id"]]
        self.assertEqual(member_names, ["Leg_BL", "Leg_BR", "Leg_FL", "Leg_FR"])

    def test_case6_same_dims_different_orientation_same_master(self):
        """CASE 6: 같은 dims, 다른 rotation → 같은 geometry master (방향은 placement 정보)."""
        p1 = make_part("Leg_01", self.SAME)
        p2 = make_part("Leg_02", self.SAME)
        p2["transform"]["rotation_euler"] = [0.0, 0.0, 1.5707963]  # 90도 회전
        clusters = ext.cluster_parts([p1, p2])
        self.assertEqual(len(clusters["master_parts"]), 1,
                         "orientation 차이만으로는 별도 master 가 되어서는 안 됨")
        self.assertEqual(clusters["master_parts"][0]["instance_count"], 2)

    def test_case7_different_semantic_role_same_dims_separate_masters(self):
        """CASE 7: role 이 다르면(Top vs Leg) 같은 dims 라도 별도 처리되어야 함."""
        # Top 과 Leg 는 group_key 자체가 다르므로 cluster_parts 단계에서 이미 분리된다
        # (group_key 별로 묶으므로). 이는 grouping 이전 단계의 semantic role 분리이며,
        # 이 케이스는 그 전제가 유지되는지 확인한다(1개뿐이면 master 가 아니라 unique).
        top = make_part("Top", (2.0, 1.0, 0.1))
        leg = make_part("Leg_01", (2.0, 1.0, 0.1))  # 우연히 같은 dims
        clusters = ext.cluster_parts([top, leg])
        # 각각 그룹에 1개뿐이므로 master_parts 가 아니라 unique_parts 로 가야 한다
        self.assertEqual(len(clusters["master_parts"]), 0,
                         "그룹당 1개뿐이면 master 가 아니라 unique_part 여야 함")
        self.assertEqual(len(clusters["unique_parts"]), 2)
        unique_names = sorted(p["name"] for p in clusters["unique_parts"])
        self.assertEqual(unique_names, ["Leg_01", "Top"])

    def test_case8_all_distinctly_different_no_arbitrary_bisection(self):
        """
        CASE 8: 4 legs, 모두 서로 다른 크기 → 실제 유사도 기준으로 그룹화해야 하며
        (경우에 따라 4개 모두 별도 master), 임의의 median/rank 이분법으로 뭉쳐서는 안 됨.
        """
        parts = [
            make_part("Leg_01", (0.05, 0.05, 0.40)),
            make_part("Leg_02", (0.10, 0.10, 0.80)),
            make_part("Leg_03", (0.15, 0.15, 1.20)),
            make_part("Leg_04", (0.20, 0.20, 1.60)),
        ]
        clusters = ext.cluster_parts(parts)
        # 모두 서로 편차가 크므로(> tolerance), 강제로 2:2 로 묶이지 않고
        # 개별 유사도에 따라 그룹화되어야 한다. 최소 요구사항: 임의의 고정된
        # "항상 절반씩" 규칙이 아니라, 실제 pairwise 유사도 결과를 반영해야 한다.
        counts = sorted(m["instance_count"] for m in clusters["master_parts"])
        total_members = sum(counts) + len(clusters["unique_parts"])
        self.assertEqual(total_members, 4)
        # 이 케이스에서는 4개가 모두 서로 다르므로, 2:2 로 묶이는 것이 우연이 아니라
        # 실제 유사도 판정 결과였는지 확인하기 위해 counts 가 [2,2] 로 고정되지
        # 않는지(즉 median split 강제가 아닌지) 완화된 형태로만 검증한다:
        # 최소한 "모두 1개짜리 master 이거나 uniqueus" 이거나, tolerance 를 만족하는
        # 실제 pair 만 묶였는지 확인.
        if counts:
            self.assertNotEqual(counts, [2, 2],
                                "임의의 median/rank 2분할이 아니라 실제 유사도로 그룹화되어야 함 "
                                "(이 케이스는 모든 쌍이 서로 다르므로 2:2 로 강제 묶이면 안 됨)")


if __name__ == "__main__":
    unittest.main(verbosity=2)