bl_info = {
    "name":        "AI Material Generator",
    "author":      "Soroush",
    "version":     (0, 2, 5),
    "blender":     (4, 5, 0),
    "location":    "3D View > Sidebar > AI MatGen",
    "description": "Generate PBR materials from text prompts via HF Inference API",
    "category":    "Material",
}

import bpy, os, sys, io, tempfile, webbrowser, subprocess, zipfile, shutil
from bpy.props import StringProperty
from bpy.types import AddonPreferences, Operator, Panel

# ────────────────────────────────────────
# 1) Resolve this file's folder absolutely
HERE     = os.path.dirname(os.path.abspath(__file__))
DEPS_ZIP = os.path.join(HERE, "deps.zip")
DEPS_DIR = os.path.join(HERE, "deps")

# 2) Ensure deps are available. When using deps.zip we need to extract it
#    because compiled modules like Pillow cannot be imported directly from a zip.
def _prepare_deps():
    if os.path.isfile(DEPS_ZIP):
        temp_path = os.path.join(tempfile.gettempdir(), "ai_matgen_deps")
        # re-extract if the zip changed or the dir is missing
        if (not os.path.isdir(temp_path) or
                os.path.getmtime(DEPS_ZIP) > os.path.getmtime(temp_path)):
            shutil.rmtree(temp_path, ignore_errors=True)
            os.makedirs(temp_path, exist_ok=True)
            with zipfile.ZipFile(DEPS_ZIP, 'r') as zf:
                zf.extractall(temp_path)
        if temp_path not in sys.path:
            sys.path.insert(0, temp_path)
        return True
    elif os.path.isdir(DEPS_DIR):
        if DEPS_DIR not in sys.path:
            sys.path.insert(0, DEPS_DIR)
        return True
    return False

_DEPS_READY = _prepare_deps()

try:
    if _DEPS_READY:
        import requests
        from PIL import Image
    else:
        raise ImportError
except Exception:
    _DEPS_READY = False

# ────────────────────────────────────────
class AIMaterialGeneratorPreferences(AddonPreferences):
    bl_idname = __name__

    hf_token: StringProperty(
        name="HF API Token",
        description="Hugging Face token with Read scope",
        subtype='PASSWORD',
        default=""
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "hf_token")
        layout.operator("wm.open_hf_read_token_page", icon='URL')
        layout.separator()
        layout.label(text="If deps are missing:")
        layout.operator("wm.install_ai_matgen_deps", icon='PACKAGE')


class InstallDependenciesOperator(Operator):
    bl_idname = "wm.install_ai_matgen_deps"
    bl_label  = "Install Dependencies"
    bl_description = "Installs requests & pillow into this add-on’s deps.zip"

    def execute(self, context):
        # 1) Clear old deps folder
        if os.path.isdir(DEPS_DIR):
            shutil.rmtree(DEPS_DIR)
        os.makedirs(DEPS_DIR, exist_ok=True)

        # 2) pip-install into deps/
        cmd = [
            sys.executable, "-m", "pip",
            "install", "--upgrade",
            "--target", DEPS_DIR,
            "requests", "pillow"
        ]
        try:
            subprocess.check_call(cmd)
        except Exception as e:
            self.report({'ERROR'}, f"pip install failed:\n{e}")
            return {'CANCELLED'}

        # 3) Zip it up for Blender’s policy scanner
        if os.path.isdir(DEPS_DIR):
            if os.path.isfile(DEPS_ZIP):
                os.remove(DEPS_ZIP)
            with zipfile.ZipFile(DEPS_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(DEPS_DIR):
                    for fn in files:
                        full = os.path.join(root, fn)
                        rel  = os.path.relpath(full, DEPS_DIR)
                        zf.write(full, rel)
            shutil.rmtree(DEPS_DIR, ignore_errors=True)

        self.report({'INFO'}, "Dependencies installed into deps.zip — restart Blender")
        return {'FINISHED'}


class HUGGINGFACE_OT_open_hf_read_token_page(Operator):
    bl_idname = "wm.open_hf_read_token_page"
    bl_label  = "Create Read Token…"
    bl_description = "Open HF tokens page with Read pre-selected"

    def execute(self, context):
        webbrowser.open("https://huggingface.co/settings/tokens/new?tokenType=read")
        return {'FINISHED'}


class AIMaterialGeneratorPanel(Panel):
    bl_label      = "AI Material Generator"
    bl_idname     = "VIEW3D_PT_ai_matgen"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category   = "AI MatGen"

    def draw(self, context):
        layout = self.layout
        prefs  = context.preferences.addons[__name__].preferences

        if not _DEPS_READY:
            layout.label(text="Dependencies missing!", icon='ERROR')
            layout.label(text="Install in Preferences", icon='INFO')
            return
        if not prefs.hf_token:
            layout.label(text="Enter HF API token in Preferences", icon='ERROR')
            return

        layout.prop(context.scene, "ai_matgen_prompt", text="Prompt")
        layout.operator("wm.generate_ai_material", text="Generate Material")


class GenerateAIMaterialOperator(Operator):
    bl_idname = "wm.generate_ai_material"
    bl_label  = "Generate AI Material"

    def execute(self, context):
        prefs  = context.preferences.addons[__name__].preferences
        prompt = context.scene.ai_matgen_prompt.strip()
        if not prompt:
            self.report({'ERROR'}, "Please enter a prompt.")
            return {'CANCELLED'}

        API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
        headers = {"Authorization": f"Bearer {prefs.hf_token}"}
        try:
            resp = requests.post(API_URL, headers=headers, json={"inputs": prompt})
            resp.raise_for_status()
            img  = Image.open(io.BytesIO(resp.content))
        except Exception as e:
            self.report({'ERROR'}, f"Generation failed: {e}")
            return {'CANCELLED'}

        # Quick PBR maps
        maps = {
            "albedo":    img,
            "roughness": img.convert("L"),
            "normal":    img,
        }

        tmp = tempfile.mkdtemp()
        img_nodes = {}
        for name, pil in maps.items():
            fp = os.path.join(tmp, f"{name}.png")
            pil.save(fp)
            img_nodes[name] = bpy.data.images.load(fp)

        mat = bpy.data.materials.new(name=f"AI: {prompt}")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        out  = nodes.new("ShaderNodeOutputMaterial")
        out.location = (400, 0)
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

        y = 200
        for nm, img in img_nodes.items():
            tex = nodes.new("ShaderNodeTexImage"); tex.image = img; tex.location = (0, y)
            if nm == "albedo":
                links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
            elif nm == "roughness":
                links.new(tex.outputs['Color'], bsdf.inputs['Roughness'])
            else:
                tex.image.colorspace_settings.name = 'Non-Color'
                nmap = nodes.new("ShaderNodeNormalMap")
                nmap.inputs['Strength'].default_value = 0.1
                nmap.location = (200, y)
                links.new(tex.outputs['Color'], nmap.inputs['Color'])
                links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
            y -= 200

        obj = context.active_object
        if obj:
            obj.data.materials.clear()
            obj.data.materials.append(mat)

        self.report({'INFO'}, "Material generated and applied.")
        return {'FINISHED'}


classes = (
    AIMaterialGeneratorPreferences,
    InstallDependenciesOperator,
    HUGGINGFACE_OT_open_hf_read_token_page,
    AIMaterialGeneratorPanel,
    GenerateAIMaterialOperator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ai_matgen_prompt = StringProperty(
        name="Prompt", description="Text prompt for material generation", default=""
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ai_matgen_prompt

if __name__ == "__main__":
    register()
