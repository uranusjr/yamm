from __future__ import annotations

import logging
import random
import time
from typing import NamedTuple, List

import numpy as np

from yamm.constructs.match import Match
from yamm.constructs.road import Road
from yamm.constructs.trace import Trace
from yamm.matchers.lcss.utils import compress
from yamm.utils.geo import road_to_coord_dist, coord_to_coord_dist

log = logging.getLogger(__name__)


class CuttingPoint(NamedTuple):
    trace_index: int


class TrajectorySegment(NamedTuple):
    """
    represents a trace and path matching
    """

    trace: Trace
    path: List[Road]

    matches: List[Match] = []

    score: float = 0

    cutting_points: List[CuttingPoint] = []

    def __add__(self, other):
        new_traces = self.trace + other.trace
        new_paths = self.path + other.path
        return TrajectorySegment(new_traces, new_paths)

    def set_score(self, score: float):
        return self._replace(score=score)

    def set_cutting_points(self, cutting_points):
        return self._replace(cutting_points=cutting_points)

    def set_matches(self, matches):
        return self._replace(matches=matches)

    def score_and_match(
        self,
        distance_epsilon: float,
        max_distance: float,
    ) -> TrajectorySegment:
        """
        computes the score of a trace, pair matching and also matches the coordinates to the nearest road.

        :param distance_epsilon
        :param max_distance

        return: updated trajectory segment with a score and matched points
        """
        trace = self.trace
        path = self.path

        m = len(trace.coords)
        n = len(path)

        matched_roads = []

        if m < 1:
            # todo: find a better way to handle this edge case
            raise Exception(f"traces of 0 points can't be matched")
        elif n < 2:
            # a path was not found for this segment; might not be matchable;
            # we set a score of zero and return a set of no-matches
            matches = [
                Match(road=None, distance=np.inf, coordinate=c)
                for c in self.trace.coords
            ]
            return self.set_score(0).set_matches(matches)

        C = [[0 for i in range(n + 1)] for j in range(m + 1)]

        f = trace._frame
        distances = np.array([f.distance(r.geom).values for r in path])

        for i in range(1, m + 1):
            nearest_road = None
            min_dist = np.inf
            coord = trace.coords[i - 1]
            for j in range(1, n + 1):
                road = path[j - 1]

                # dt = road_to_coord_dist(road, coord)
                dt = distances[j - 1][i - 1]

                if dt < min_dist:
                    min_dist = dt
                    nearest_road = road

                if dt < distance_epsilon:
                    point_similarity = 1 - (dt / distance_epsilon)
                else:
                    point_similarity = 0

                C[i][j] = max(
                    (C[i - 1][j - 1] + point_similarity), C[i][j - 1], C[i - 1][j]
                )

            if min_dist > max_distance:
                nearest_road = None
                min_dist = np.inf

            match = Match(
                road=nearest_road,
                distance=min_dist,
                coordinate=coord,
            )
            matched_roads.append(match)

        sim_score = C[m][n] / float(min(m, n))

        return self.set_score(sim_score).set_matches(matched_roads)

    def compute_cutting_points(
        self,
        distance_epsilon: float,
        cutting_thresh: float,
        random_cuts: int,
    ) -> TrajectorySegment:
        """
        Computes the cutting points for a trajectory segment by:
         - computing the furthest point
         - adding points that are close to the distance epsilon

        :param distance_epsilon:
        :param cutting_thresh:
        :param random_cuts:

        :return: the updated trajectory segment with cutting points
        """
        cutting_points = []

        no_match = all([not m.road for m in self.matches])

        if not self.path or no_match:
            # no path computed or no matches found, possible edge cases:
            # 1. trace starts and ends in the same location: pick points far from the start and end
            start = self.trace.coords[0]
            end = self.trace.coords[-1]

            start_end_dist = start.geom.distance(end.geom)

            if start_end_dist < distance_epsilon:
                p1 = np.argmax(
                    [coord_to_coord_dist(start, c) for c in self.trace.coords]
                )
                p2 = np.argmax([coord_to_coord_dist(end, c) for c in self.trace.coords])

                cp1 = CuttingPoint(p1)
                cp2 = CuttingPoint(p2)

                cutting_points.extend([cp1, cp2])
            else:
                # pick the middle point on the trace:
                mid = int(len(self.trace) / 2)
                cp = CuttingPoint(mid)
                cutting_points.append(cp)
        else:
            # find furthest point
            i = np.argmax([m.distance for m in self.matches if m.road])
            cutting_points.append(CuttingPoint(i))

            # collect points that are close to the distance threshold
            for i, m in enumerate(self.matches):
                if m.road:
                    if abs(m.distance - distance_epsilon) < cutting_thresh:
                        cutting_points.append(CuttingPoint(i))

        # add random points
        for _ in range(random_cuts):
            cpi = random.randint(0, len(self.trace) - 1)
            cutting_points.append(CuttingPoint(cpi))

        # merge cutting points that are adjacent to one another
        compressed_cuts = list(compress(cutting_points))

        # it doesn't make sense to cut the trace at the start or end so discard any
        # points that apear in the [0, 1, -1, -2] position with respect to a trace
        n = len(self.trace)
        final_cuts = list(
            filter(
                lambda cp: cp.trace_index not in [0, 1, n - 2, n - 1], compressed_cuts
            )
        )

        return self.set_cutting_points(final_cuts)


TrajectoryScheme = List[TrajectorySegment]
