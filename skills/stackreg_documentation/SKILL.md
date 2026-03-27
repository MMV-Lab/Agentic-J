---
name: stackreg_documentation
description: An ImageJ plugin from EPFL BIG that aligns all slices of a stack by
 **sequential propagation** — each slice is registered to the previous one,
 starting from the current anchor slice. Uses TurboReg internally for each pairwise registration.
 Primary use cases are time-lapse drift correction, serial section alignment, Z-stack stabilisation.
 Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---

## StackReg vs TurboReg — Key Differences

| | StackReg | TurboReg |
|---|---|---|
| Aligns | All slices of a stack sequentially | One source image to one target |
| Recordable | ✅ Yes | ❌ No |
| Bilinear | ❌ Not available | ✅ Available |
| Modifies original | ✅ Yes — in-place | ❌ No — new window |
| Scripting | `IJ.run("StackReg ", ...)` | `IJ.run("TurboReg ", ...)` |
| Internally uses | TurboReg via `-file` + `-hideOutput` | Own algorithm |

---

## Automation via Groovy?

**YES — and it is simpler than TurboReg** because StackReg IS macro-recordable.

```groovy
IJ.run("StackReg ", "transformation=[Rigid Body]")
```

The trailing space in `"StackReg "` is **mandatory** — same as TurboReg.

---

## Full Syntax

```groovy
IJ.run("StackReg ", "transformation=[<TYPE>]")
```

| `<TYPE>` | Notes |
|---|---|
| `Translation` | XY drift only |
| `Rigid Body` | Drift + rotation |
| `Scaled Rotation` | Drift + rotation + isotropic scale |
| `Affine` | Full 2D linear |

Bilinear is NOT available (cannot be propagated between slices).

---

## Anchor Slice

StackReg uses the **currently displayed slice** as its anchor (not transformed;
all other slices align outward from it). Set it in Groovy with:

```groovy
imp.setSlice(anchorSliceNumber)   // 1-based
IJ.run(imp, "StackReg ", "transformation=[Rigid Body]")
```

Best practice: choose a central, sharp, representative slice as anchor.

---

## In-Place Modification

StackReg **replaces the original stack** — always duplicate first if you need
the original:

```groovy
import ij.plugin.Duplicator
def registered = new Duplicator().run(imp)
registered.show()
IJ.run(registered, "StackReg ", "transformation=[Translation]")
```

---

## How StackReg Calls TurboReg Internally

For each adjacent slice pair, StackReg:
1. Writes both slices as float TIFFs to the ImageJ temp directory
   (`StackRegSource`, `StackRegTarget`)
2. Calls `IJ.runPlugIn("TurboReg_", "-align -file ... -hideOutput")`
3. Retrieves the refined landmark coordinates from TurboReg
4. Propagates those coordinates as starting positions for the next slice

Temp files are overwritten each iteration. TurboReg must be installed or
StackReg fails silently mid-stack.

---

## Critical Pitfalls

1. **Missing trailing space** in `"StackReg "` — silently does nothing
2. **Original stack is overwritten** — always duplicate before registering
3. **Anchor slice not set** before calling `IJ.run()` — defaults to whatever
   slice is currently displayed
4. **TurboReg not installed** — StackReg fails mid-registration without a
   clear error
5. **Bilinear not available** — requesting it causes the parameter to be
   unrecognised
6. **Long stacks + Affine** — propagation error accumulates; use Translation
   or Rigid Body unless affine is genuinely needed

---

## File Inventory

| File | Contents |
|---|---|
| `OVERVIEW.md` | Plugin description, TurboReg relationship, transformation types, installation |
| `UI_GUIDE.md` | Every dialog control, anchor behaviour, colour handling, temp files |
| `UI_WORKFLOW_REGISTRATION.md` | Step-by-step GUI walkthroughs (single stack, colour, multi-channel) |
| `GROOVY_SCRIPT_API.md` | Full API, 6 Groovy recipes, TurboReg internals |
| `WORKFLOW_BATCH_REGISTRATION.groovy` | Ready-to-run batch registration script |
| `SKILL.md` | This quick-reference card |
