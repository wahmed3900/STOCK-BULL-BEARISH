
import os
import shutil

# Define folders
root = os.getcwd()
services_dir = os.path.join(root, "services")
templates_dir = os.path.join(root, "templates")
components_dir = os.path.join(templates_dir, "components")

# Create services folder if it doesn't exist
os.makedirs(services_dir, exist_ok=True)

# Move all .py files from templates/ to services/
for file in os.listdir(templates_dir):
    if file.endswith(".py"):
        src = os.path.join(templates_dir, file)
        dst = os.path.join(services_dir, file)
        if os.path.exists(dst):
            print(f"⚠️ Skipping duplicate: {file}")
        else:
            shutil.move(src, dst)
            print(f"✅ Moved {file} to services/")

# Move all .py files from components/ to services/
for file in os.listdir(components_dir):
    if file.endswith(".py"):
        src = os.path.join(components_dir, file)
        dst = os.path.join(services_dir, file)
        if os.path.exists(dst):
            print(f"⚠️ Skipping duplicate: {file}")
        else:
            shutil.move(src, dst)
            print(f"✅ Moved {file} to services/")

print("\n🎉 All Python files are now in services/")
print("📁 Your templates/ and components/ folders now only have HTML files.")