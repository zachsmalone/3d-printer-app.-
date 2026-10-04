"""Generate a synthetic sample photo (gradient sky, sun, hills, a face-like blob)."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

def make(path="sample.png", w=480, h=360):
    y, x = np.mgrid[0:h, 0:w]
    sky = np.stack([60 + 120 * y / h, 120 + 100 * y / h, 220 - 40 * y / h], -1)
    im = Image.fromarray(sky.astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.ellipse([w * .65, h * .1, w * .85, h * .1 + w * .2], fill=(255, 220, 60))
    d.polygon([(0, h), (0, h * .65), (w * .3, h * .45), (w * .55, h * .7), (w * .8, h * .5), (w, h * .68), (w, h)], fill=(40, 110, 50))
    d.ellipse([w * .25, h * .35, w * .5, h * .75], fill=(230, 170, 140))
    d.ellipse([w * .31, h * .47, w * .35, h * .52], fill=(30, 30, 30))
    d.ellipse([w * .40, h * .47, w * .44, h * .52], fill=(30, 30, 30))
    d.arc([w * .31, h * .55, w * .44, h * .68], 20, 160, fill=(150, 30, 30), width=5)
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    im.save(path)
    return path

if __name__ == "__main__":
    print(make(sys.argv[1] if len(sys.argv) > 1 else "sample.png"))
