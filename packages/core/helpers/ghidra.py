#!/usr/bin/env python2
# script/ghidra.py

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os

# Read output dir from postScript args; fallback if omitted
args = getScriptArgs()
output_dir = args[0] if args and len(args) >= 1 else "/tmp/decompiled"

if not os.path.isdir(output_dir):
    os.makedirs(output_dir)

decomp = DecompInterface()
decomp.openProgram(currentProgram)

program_name = currentProgram.getName()
safe_base, _ = os.path.splitext(program_name)
out_path = os.path.join(output_dir, safe_base + "_decompiled.c")

with open(out_path, "w") as out_file:
    fm = currentProgram.getFunctionManager()
    it = fm.getFunctions(True)
    while it.hasNext():
        func = it.next()
        out_file.write("// Function: %s\n" % func.getName())
        res = decomp.decompileFunction(func, 0, ConsoleTaskMonitor())
        df = res.getDecompiledFunction()
        if df is not None:
            out_file.write(df.getC())
            out_file.write("\n\n")

print("[GhidraScript] Decompiled %s to %s" % (program_name, out_path))