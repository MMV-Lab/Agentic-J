# Fine-tuned Cellpose models

Drop your own fine-tuned/custom Cellpose model file(s) here (e.g. a model saved by
`cellpose --train` or the Cellpose GUI's training tab — no file extension is normal for
these, matching Cellpose's own built-in models). This folder is the host `./data/fine-tuned-models`
directory, mounted straight through into the container at `/app/data/fine-tuned-models`.

## Expected file format

A raw PyTorch `state_dict` (`torch.save(model.state_dict(), path)`), not a full pickled
model, ONNX, or safetensors file — Cellpose loads it with `weights_only=True`, which
rejects anything else.

The key names must match whichever architecture you fine-tuned from — the two are **not
interchangeable**:
- Fine-tuned from a **v3 model** (`cyto3`, `nucleitorch_0`, ...) → use the `Cellpose`
  Groovy command (`env_path = ".../envs/cellpose"`).
- Fine-tuned from **Cellpose-SAM** (`cpsam`) → use the `CellposeSAM` Groovy command
  (`env_path = ".../envs/cellpose4"`) instead.

Optional: a companion `size_<name>.npy` file next to the model enables `diameter=0`
auto-estimation (like the stock `size_cyto3.npy`); without it, just pass `cp.diameter`
explicitly.

## Using it in a script

**Immediately, no restart needed** — point `model_path` at the file directly:
```groovy
cp.model = ""
cp.model_path = new File("/app/data/fine-tuned-models/my_model")
```

**As a bare model name, same as a built-in model** (`cp.model = "my_model"`) — requires
**restarting the container** once after adding the file, so the entrypoint can link it into
`~/.cellpose/models` and register it with Cellpose:
```groovy
cp.model = "my_model"
```

See `skills/cellpose_documentation/SKILL.md` → "Custom / fine-tuned models the user provides"
for the full explanation of why the restart is needed for the second form but not the first.
