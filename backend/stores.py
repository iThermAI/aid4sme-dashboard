"""Small JSON stores: camera settings profiles and part presets."""
import json
import os
import re
import shutil
import unicodedata


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-._")
    return s[:60] or "item"


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


class JsonStore(object):
    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def path(self, slug):
        if os.path.basename(slug) != slug or not slug:
            raise KeyError(slug)
        return os.path.join(self.folder, slug + ".json")

    def unique_slug(self, name):
        base = slugify(name)
        slug, n = base, 1
        while os.path.exists(self.path(slug)):
            n += 1
            slug = "%s-%d" % (base, n)
        return slug

    def save(self, slug, obj):
        _write(self.path(slug), obj)

    def load(self, slug):
        with open(self.path(slug), encoding="utf-8") as f:
            return json.load(f)

    def delete(self, slug):
        os.remove(self.path(slug))
        extra = os.path.join(self.folder, slug + ".glb")
        if os.path.isfile(extra):
            os.remove(extra)

    def all(self):
        out = []
        for fn in sorted(os.listdir(self.folder)):
            if fn.endswith(".json"):
                try:
                    obj = self.load(fn[:-5])
                except (OSError, ValueError):
                    continue
                obj["slug"] = fn[:-5]
                out.append(obj)
        return out

    def attach(self, slug, src, ext=".glb"):
        dest = os.path.join(self.folder, slug + ext)
        shutil.copyfile(src, dest)
        return dest
