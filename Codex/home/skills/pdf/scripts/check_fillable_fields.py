import sys
from pypdf import PdfReader
from portable_safety import PortablePathError, resolve_inside


def main():
    if len(sys.argv) != 2:
        print("Usage: check_fillable_fields.py [input pdf]", file=sys.stderr)
        raise SystemExit(1)
    try:
        path = resolve_inside(sys.argv[1], must_exist=True, kind="file")
    except (FileNotFoundError, PortablePathError) as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    reader = PdfReader(str(path))
    if reader.get_fields():
        print("This PDF has fillable form fields")
    else:
        print("This PDF does not have fillable form fields; you will need to visually determine where to enter data")


if __name__ == "__main__":
    main()
