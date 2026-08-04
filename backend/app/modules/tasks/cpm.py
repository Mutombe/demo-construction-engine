"""Critical path analysis over the task network.

Pure date arithmetic on data the schedule already holds — no new data entry.
Durations come from planned_start/planned_end; the four dependency types and
their lag are honoured exactly as the Gantt draws them.

Convention: dates are inclusive, so a task starting and ending on the same day
has a duration of one day, and an FS successor starts the day AFTER its
predecessor finishes (plus any lag).
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from app.common.enums import DependencyType

DAY = timedelta(days=1)


@dataclass
class TaskNode:
    id: uuid.UUID
    start: date
    end: date

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass
class CpmResult:
    early_start: dict[uuid.UUID, date]
    early_finish: dict[uuid.UUID, date]
    late_start: dict[uuid.UUID, date]
    late_finish: dict[uuid.UUID, date]
    total_float: dict[uuid.UUID, int]
    critical: set[uuid.UUID]
    project_finish: date | None


def _topological_order(
    node_ids: list[uuid.UUID], edges: list[tuple[uuid.UUID, uuid.UUID, DependencyType, int]]
) -> list[uuid.UUID] | None:
    """Kahn's algorithm. Returns None if the network contains a cycle.

    Cycles are already rejected when dependencies are created, so None here
    means the data is corrupt — callers degrade to "no CPM" rather than hang.
    """
    incoming: dict[uuid.UUID, int] = {nid: 0 for nid in node_ids}
    outgoing: dict[uuid.UUID, list[uuid.UUID]] = {nid: [] for nid in node_ids}
    for predecessor, successor, _, _ in edges:
        if predecessor not in incoming or successor not in incoming:
            continue
        outgoing[predecessor].append(successor)
        incoming[successor] += 1

    queue = [nid for nid, count in incoming.items() if count == 0]
    order: list[uuid.UUID] = []
    while queue:
        current = queue.pop(0)
        order.append(current)
        for successor in outgoing[current]:
            incoming[successor] -= 1
            if incoming[successor] == 0:
                queue.append(successor)
    return order if len(order) == len(node_ids) else None


def compute(
    tasks: list[TaskNode],
    edges: list[tuple[uuid.UUID, uuid.UUID, DependencyType, int]],
) -> CpmResult:
    """Forward and backward pass over the network.

    Tasks without both planned dates are excluded by the caller: they have no
    duration, so they cannot sit on a critical path.
    """
    empty = CpmResult({}, {}, {}, {}, {}, set(), None)
    if not tasks:
        return empty

    nodes = {task.id: task for task in tasks}
    order = _topological_order(list(nodes), edges)
    if order is None:
        return empty

    predecessors: dict[uuid.UUID, list[tuple[uuid.UUID, DependencyType, int]]] = {
        nid: [] for nid in nodes
    }
    successors: dict[uuid.UUID, list[tuple[uuid.UUID, DependencyType, int]]] = {
        nid: [] for nid in nodes
    }
    for predecessor, successor, dep_type, lag in edges:
        if predecessor not in nodes or successor not in nodes:
            continue
        predecessors[successor].append((predecessor, dep_type, lag))
        successors[predecessor].append((successor, dep_type, lag))

    # --- Forward pass: earliest each task can start without breaking a link
    early_start: dict[uuid.UUID, date] = {}
    early_finish: dict[uuid.UUID, date] = {}
    for nid in order:
        node = nodes[nid]
        start = node.start
        finish_floor: date | None = None
        for pred_id, dep_type, lag in predecessors[nid]:
            lag_delta = timedelta(days=lag)
            if dep_type == DependencyType.FS:
                start = max(start, early_finish[pred_id] + DAY + lag_delta)
            elif dep_type == DependencyType.SS:
                start = max(start, early_start[pred_id] + lag_delta)
            elif dep_type == DependencyType.FF:
                candidate = early_finish[pred_id] + lag_delta
                finish_floor = candidate if finish_floor is None else max(finish_floor, candidate)
            elif dep_type == DependencyType.SF:
                candidate = early_start[pred_id] + lag_delta
                finish_floor = candidate if finish_floor is None else max(finish_floor, candidate)
        finish = start + node.duration
        if finish_floor is not None and finish_floor > finish:
            # Finish-constrained link pushes the whole task out, keeping duration
            finish = finish_floor
            start = finish - node.duration
        early_start[nid] = start
        early_finish[nid] = finish

    project_finish = max(early_finish.values())

    # --- Backward pass: latest each task can run without delaying the project
    late_finish: dict[uuid.UUID, date] = {}
    late_start: dict[uuid.UUID, date] = {}
    for nid in reversed(order):
        node = nodes[nid]
        finish = project_finish
        start_ceiling: date | None = None
        for succ_id, dep_type, lag in successors[nid]:
            lag_delta = timedelta(days=lag)
            if dep_type == DependencyType.FS:
                finish = min(finish, late_start[succ_id] - DAY - lag_delta)
            elif dep_type == DependencyType.FF:
                finish = min(finish, late_finish[succ_id] - lag_delta)
            elif dep_type == DependencyType.SS:
                candidate = late_start[succ_id] - lag_delta
                start_ceiling = (
                    candidate if start_ceiling is None else min(start_ceiling, candidate)
                )
            elif dep_type == DependencyType.SF:
                candidate = late_finish[succ_id] - lag_delta
                start_ceiling = (
                    candidate if start_ceiling is None else min(start_ceiling, candidate)
                )
        start = finish - node.duration
        if start_ceiling is not None and start_ceiling < start:
            start = start_ceiling
            finish = start + node.duration
        late_finish[nid] = finish
        late_start[nid] = start

    total_float = {nid: (late_start[nid] - early_start[nid]).days for nid in nodes}
    critical = {nid for nid, slack in total_float.items() if slack <= 0}

    return CpmResult(
        early_start=early_start,
        early_finish=early_finish,
        late_start=late_start,
        late_finish=late_finish,
        total_float=total_float,
        critical=critical,
        project_finish=project_finish,
    )
