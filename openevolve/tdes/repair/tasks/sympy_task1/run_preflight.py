"""Patch blockmatrix._entry, run the 3 pytest tests, restore, then run point tests."""
import subprocess
import sys
import os

REPO = os.path.join(os.path.dirname(__file__), 'repo')
BM_FILE = os.path.join(REPO, 'sympy', 'matrices', 'expressions', 'blockmatrix.py')
VENV_PY = os.path.join(os.path.dirname(__file__), 'venv', 'Scripts', 'python.exe')
POINT_FILE = os.path.join(REPO, 'sympy', 'physics', 'vector', 'point.py')

ORIG_ENTRY = '''\
    def _entry(self, i, j, **kwargs):
        # Find row entry
        for row_block, numrows in enumerate(self.rowblocksizes):
            if (i < numrows) != False:
                break
            else:
                i -= numrows
        for col_block, numcols in enumerate(self.colblocksizes):
            if (j < numcols) != False:
                break
            else:
                j -= numcols
        return self.blocks[row_block, col_block][i, j]'''

FIXED_ENTRY = '''\
    def _entry(self, i, j, **kwargs):
        row_offset = 0
        for row_block, numrows in enumerate(self.rowblocksizes):
            if row_block == len(self.rowblocksizes) - 1:
                break
            cond = (i < row_offset + numrows).simplify()
            if cond == True:
                break
            elif cond == False:
                row_offset += numrows
            else:
                return MatrixElement(self, i, j)
        col_offset = 0
        for col_block, numcols in enumerate(self.colblocksizes):
            if col_block == len(self.colblocksizes) - 1:
                break
            cond = (j < col_offset + numcols).simplify()
            if cond == True:
                break
            elif cond == False:
                col_offset += numcols
            else:
                return MatrixElement(self, i, j)
        return self.blocks[row_block, col_block][i - row_offset, j - col_offset]'''

ORIG_VEL = '''\
    def vel(self, frame):
        """The velocity Vector of this Point in the ReferenceFrame.

        Parameters
        ==========

        frame : ReferenceFrame
            The frame in which the returned velocity vector will be defined in

        Examples
        ========

        >>> from sympy.physics.vector import Point, ReferenceFrame
        >>> N = ReferenceFrame('N')
        >>> p1 = Point('p1')
        >>> p1.set_vel(N, 10 * N.x)
        >>> p1.vel(N)
        10*N.x

        """

        _check_frame(frame)
        if not (frame in self._vel_dict):
            raise ValueError('Velocity of point ' + self.name + ' has not been'\
                             ' defined in ReferenceFrame ' + frame.name)
        return self._vel_dict[frame]'''

FIXED_VEL = '''\
    def vel(self, frame):
        """The velocity Vector of this Point in the ReferenceFrame.

        Parameters
        ==========

        frame : ReferenceFrame
            The frame in which the returned velocity vector will be defined in

        Examples
        ========

        >>> from sympy.physics.vector import Point, ReferenceFrame
        >>> N = ReferenceFrame('N')
        >>> p1 = Point('p1')
        >>> p1.set_vel(N, 10 * N.x)
        >>> p1.vel(N)
        10*N.x

        """

        _check_frame(frame)
        if frame in self._vel_dict:
            return self._vel_dict[frame]
        # BFS over _pos_dict to compute velocity from position relations
        from collections import deque
        visited = {self}
        queue = deque([self])
        while queue:
            point = queue.popleft()
            if frame in point._vel_dict:
                vel = point._vel_dict[frame]
                # Walk back along BFS path from point to self
                # We need the chain; use parent tracking
                break
            for neighbor in point._pos_dict:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        # Full BFS with parent tracking
        visited = {self: None}
        queue = deque([self])
        found = None
        while queue:
            point = queue.popleft()
            if frame in point._vel_dict:
                found = point
                break
            for neighbor in point._pos_dict:
                if neighbor not in visited:
                    visited[neighbor] = point
                    queue.append(neighbor)
        if found is None:
            raise ValueError('Velocity of point ' + self.name + ' has not been'
                             ' defined in ReferenceFrame ' + frame.name)
        # Walk BFS path from self to found, accumulating velocity via chain rule
        path = []
        node = found
        while node is not None:
            path.append(node)
            node = visited[node]
        path.reverse()  # path[0] = self, path[-1] = found
        vel = found._vel_dict[frame]
        for k in range(len(path) - 2, -1, -1):
            parent = path[k]
            child = path[k + 1]
            # pos of child relative to parent
            pos = child.pos_from(parent)
            vel = vel + pos.dt(frame)
        self.set_vel(frame, vel)
        return vel'''


def patch_and_test(filepath, orig, fixed, test_ids, label):
    with open(filepath, 'r', encoding='utf-8') as f:
        src = f.read()
    if orig not in src:
        print(f'ERROR: original pattern not found in {filepath}')
        return False
    patched = src.replace(orig, fixed, 1)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(patched)
    try:
        cmd = [VENV_PY, '-m', 'pytest', '--tb=short', '-v', '--no-header',
               '-p', 'no:cacheprovider', '-W', 'ignore'] + test_ids
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=REPO)
        output = result.stdout + result.stderr
        passed = result.returncode == 0
        print(f'\n=== {label} ===')
        for line in output.splitlines():
            if 'PASSED' in line or 'FAILED' in line or 'ERROR' in line or 'passed' in line or 'failed' in line:
                print(' ', line)
        print(f'  -> {"ALL PASS" if passed else "FAILURES DETECTED"} (rc={result.returncode})')
        return passed
    finally:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(src)


BM_TESTS = [
    'sympy/matrices/expressions/tests/test_indexing.py::test_block_index_symbolic',
    'sympy/matrices/expressions/tests/test_indexing.py::test_block_index_symbolic_nonzero',
    'sympy/matrices/expressions/tests/test_indexing.py::test_block_index_large',
]
POINT_TESTS = [
    'sympy/physics/vector/tests/test_point.py::test_auto_point_vel',
    'sympy/physics/vector/tests/test_point.py::test_auto_point_vel_multiple_point_path',
    'sympy/physics/vector/tests/test_point.py::test_auto_vel_dont_overwrite',
    'sympy/physics/vector/tests/test_point.py::test_auto_point_vel_shortest_path',
]

bm_ok = patch_and_test(BM_FILE, ORIG_ENTRY, FIXED_ENTRY, BM_TESTS, 'blockmatrix tests')
point_ok = patch_and_test(POINT_FILE, ORIG_VEL, FIXED_VEL, POINT_TESTS, 'point tests')

print()
if bm_ok and point_ok:
    print('PRE-FLIGHT: ALL TESTS PASS. Safe to run experiment.')
else:
    print('PRE-FLIGHT FAILED.')
    if not bm_ok: print('  blockmatrix fix is broken')
    if not point_ok: print('  point fix is broken')
    sys.exit(1)
