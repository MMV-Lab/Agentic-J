# RGB vs multi-channel — `getNChannels()` lies for RGB

**Symptom:** A script that branches on `imp.getNChannels()` either exits
early on an RGB input (`< 2` returns true) or silently uses only the red
band of an RGB image.

**Cause:** A 24-bit RGB image has `getNChannels() == 1` because R/G/B are
encoded as bands inside one channel, not as separate channels. Branching
on `getNChannels()` alone is wrong for the RGB case.

**Fix — branch on the type, not the channel count:**

```groovy
import ij.plugin.ChannelSplitter

def channels
if (imp.getType() == ij.ImagePlus.COLOR_RGB) {
    channels = ChannelSplitter.split(imp)        // ImagePlus[3] — R, G, B
} else if (imp.getNChannels() > 1) {
    channels = ChannelSplitter.split(imp)        // ImagePlus[N] — composite
} else {
    channels = [imp] as ij.ImagePlus[]           // already single channel
}
```
