import sys
sys.path.insert(0, 'repo')
from sympy import symbols
from sympy.matrices.expressions.blockmatrix import BlockMatrix
from sympy.matrices.expressions.matexpr import MatrixElement
from sympy.matrices import MatrixSymbol

def _entry_fixed(self, i, j, **kwargs):
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
    return self.blocks[row_block, col_block][i - row_offset, j - col_offset]

BlockMatrix._entry = _entry_fixed
ME = MatrixElement

# ---- test_block_index_symbolic (unconstrained) ----
n,m,k,l,i,j = symbols('n m k l i j')
A1=MatrixSymbol('A1',n,k); A2=MatrixSymbol('A2',n,l)
A3=MatrixSymbol('A3',m,k); A4=MatrixSymbol('A4',m,l)
A=BlockMatrix([[A1,A2],[A3,A4]])
cases = [
    ('A[0,0]==ME',         A[0,0]==ME(A,0,0)),
    ('A[n-1,k-1]==A1',     A[n-1,k-1]==A1[n-1,k-1]),
    ('A[n,k]==A4[0,0]',    A[n,k]==A4[0,0]),
    ('A[n+m-1,0]==ME',     A[n+m-1,0]==ME(A,n+m-1,0)),
    ('A[0,k+l-1]==ME',     A[0,k+l-1]==ME(A,0,k+l-1)),
    ('A[n+m-1,k+l-1]==ME', A[n+m-1,k+l-1]==ME(A,n+m-1,k+l-1)),
    ('A[i,j]==ME',         A[i,j]==ME(A,i,j)),
    ('A[n+i,k+j]==ME',     A[n+i,k+j]==ME(A,n+i,k+j)),
    ('A[n-i-1,k-j-1]==ME', A[n-i-1,k-j-1]==ME(A,n-i-1,k-j-1)),
]
print('=== test_block_index_symbolic ===')
failed = 0
for name, ok in cases:
    status = 'PASS' if ok else 'FAIL'
    print(f'  {status}: {name}')
    if not ok: failed += 1

# ---- test_block_index_symbolic_nonzero ----
kp,lp,mp,np_ = symbols('k l m n', integer=True, positive=True)
ip,jp = symbols('i j', integer=True, nonnegative=True)
A1b=MatrixSymbol('A1',np_,kp); A2b=MatrixSymbol('A2',np_,lp)
A3b=MatrixSymbol('A3',mp,kp); A4b=MatrixSymbol('A4',mp,lp)
Ab=BlockMatrix([[A1b,A2b],[A3b,A4b]])
cases2 = [
    ('A[0,0]==A1[0,0]',            Ab[0,0]==A1b[0,0]),
    ('A[n+m-1,0]==A3[m-1,0]',      Ab[np_+mp-1,0]==A3b[mp-1,0]),
    ('A[0,k+l-1]==A2[0,l-1]',      Ab[0,kp+lp-1]==A2b[0,lp-1]),
    ('A[n+m-1,k+l-1]==A4[m-1,l-1]',Ab[np_+mp-1,kp+lp-1]==A4b[mp-1,lp-1]),
    ('A[i,j]==ME',                  Ab[ip,jp]==ME(Ab,ip,jp)),
    ('A[n+i,k+j]==A4[i,j]',        Ab[np_+ip,kp+jp]==A4b[ip,jp]),
    ('A[n-i-1,k-j-1]==A1[...]',    Ab[np_-ip-1,kp-jp-1]==A1b[np_-ip-1,kp-jp-1]),
    ('A[2*n,2*k]==A4[n,k]',        Ab[2*np_,2*kp]==A4b[np_,kp]),
]
print('=== test_block_index_symbolic_nonzero ===')
for name, ok in cases2:
    status = 'PASS' if ok else 'FAIL'
    print(f'  {status}: {name}')
    if not ok: failed += 1

# ---- test_block_index_large ----
n3,m3,k3 = symbols('n m k', integer=True, positive=True)
i3 = symbols('i', integer=True, nonnegative=True)
A1c=MatrixSymbol('A1',n3,n3); A2c=MatrixSymbol('A2',n3,m3); A3c=MatrixSymbol('A3',n3,k3)
A4c=MatrixSymbol('A4',m3,n3); A5c=MatrixSymbol('A5',m3,m3); A6c=MatrixSymbol('A6',m3,k3)
A7c=MatrixSymbol('A7',k3,n3); A8c=MatrixSymbol('A8',k3,m3); A9c=MatrixSymbol('A9',k3,k3)
Ac=BlockMatrix([[A1c,A2c,A3c],[A4c,A5c,A6c],[A7c,A8c,A9c]])
print('=== test_block_index_large ===')
ok3 = Ac[n3+i3,n3+i3]==ME(Ac,n3+i3,n3+i3)
print(f'  {"PASS" if ok3 else "FAIL"}: A[n+i,n+i]==ME')
if not ok3: failed += 1

print()
print(f'Total failures: {failed}')
if failed == 0:
    print('ALL TESTS PASS')
