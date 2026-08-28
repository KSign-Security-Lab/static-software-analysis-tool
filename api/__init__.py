"""F2-A test API — a thin FastAPI service over ssat.cpg + ssat.f2a.

It generates a Code Property Graph from submitted source (via the Joern
container, using ssat.cpg) and runs the F2-A evidence pipeline (ssat.f2a).
It deliberately does NOT touch the template/ast/dfg modules.
"""
