import os

def print_tree(start_path='.', prefix=''):
    ignore_dirs = {'.git', 'node_modules', '.venv', '__pycache__'}

    for item in sorted(os.listdir(start_path)):
        full_path = os.path.join(start_path, item)
        if os.path.isdir(full_path) and item not in ignore_dirs:
            print(f"{prefix}├── {item}/")
            print_tree(full_path, prefix + "│   ")
        elif os.path.isfile(full_path):
            print(f"{prefix}├── {item}")

print_tree()
