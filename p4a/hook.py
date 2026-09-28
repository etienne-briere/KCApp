from pathlib import Path
from pythonforandroid.toolchain import ToolchainCL

def after_apk_build(toolchain: ToolchainCL):
    manifest_file = Path(toolchain._dist.dist_dir) / "src" / "main" / "AndroidManifest.xml"

    content = manifest_file.read_text(encoding="utf-8")
    
    print("============================================== MANIFEST BEFORE")
    print(content)
    print("==============================================")
    
    indent = "    "  # 4 espaces d’indentation

    provider_fragment = f"""
    {indent}<provider
    {indent}    android:name="androidx.core.content.FileProvider"
    {indent}    android:authorities="org.m2s.apex.apex_control.fileprovider"
    {indent}    android:exported="false"
    {indent}    android:grantUriPermissions="true">
    {indent}    <meta-data
    {indent}        android:name="android.support.FILE_PROVIDER_PATHS"
    {indent}        android:resource="@xml/file_paths" />
    {indent}</provider>
    """
    

    content = content.replace(
        "</application>",
        f"{provider_fragment}\n{indent}</application>",
    )

    manifest_file.write_text(content, encoding="utf-8")

    print("============================================== MANIFEST AFTER")
    print(content)
    print("==============================================")