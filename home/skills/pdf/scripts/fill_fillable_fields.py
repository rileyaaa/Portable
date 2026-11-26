import json
import sys

# The bundled isolated Python deliberately omits the script directory.
# Use only this entrypoint's verified package-local sibling modules.
if __name__ == "__main__" and sys.flags.safe_path:
    import stat
    from pathlib import Path
    _script = Path(__file__).absolute()
    _root = _script.parents[4]
    if _script.relative_to(_root).parts != ("home", "skills", "pdf", "scripts", "fill_fillable_fields.py"):
        raise RuntimeError("Script is outside its bundled skill layout")
    _directory = _script.parent
    for _entry in (*reversed(_script.parents),):
        _info = _entry.lstat()
        if not stat.S_ISDIR(_info.st_mode) or getattr(_info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Skill import path crosses a link or non-directory")
    for _entry in (_script, _root / "env.ps1", _root / "codex.exe", _directory / "portable_safety.py", _directory / "extract_form_field_info.py"):
        _info = _entry.lstat()
        if not stat.S_ISREG(_info.st_mode) or _info.st_nlink != 1 or getattr(_info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Skill import requires ordinary single-link package files")
    sys.path.insert(0, str(_directory))
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None and not _stream.isatty() and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")


from pypdf import PdfReader, PdfWriter

from extract_form_field_info import get_field_info
from portable_safety import PortablePathError, prepare_output_file, resolve_inside




def fill_pdf_fields(input_pdf_path: str, fields_json_path: str, output_pdf_path: str):
    input_pdf_path = resolve_inside(input_pdf_path, must_exist=True, kind="file")
    fields_json_path = resolve_inside(fields_json_path, must_exist=True, kind="file")
    output_pdf_path = prepare_output_file(output_pdf_path)
    with open(fields_json_path, encoding="utf-8-sig") as f:
        fields = json.load(f)
    fields_by_page = {}
    for field in fields:
        if "value" in field:
            field_id = field["field_id"]
            page = field["page"]
            if page not in fields_by_page:
                fields_by_page[page] = {}
            fields_by_page[page][field_id] = field["value"]
    
    reader = PdfReader(input_pdf_path)

    has_error = False
    field_info = get_field_info(reader)
    fields_by_ids = {f["field_id"]: f for f in field_info}
    for field in fields:
        existing_field = fields_by_ids.get(field["field_id"])
        if not existing_field:
            has_error = True
            print(f"ERROR: `{field['field_id']}` is not a valid field ID")
        elif field["page"] != existing_field["page"]:
            has_error = True
            print(f"ERROR: Incorrect page number for `{field['field_id']}` (got {field['page']}, expected {existing_field['page']})")
        else:
            if "value" in field:
                err = validation_error_for_field_value(existing_field, field["value"])
                if err:
                    print(err)
                    has_error = True
    if has_error:
        sys.exit(1)

    writer = PdfWriter(clone_from=reader)
    for page, field_values in fields_by_page.items():
        writer.update_page_form_field_values(writer.pages[page - 1], field_values, auto_regenerate=False)

    writer.set_need_appearances_writer(True)
    
    with open(output_pdf_path, "wb") as f:
        writer.write(f)


def validation_error_for_field_value(field_info, field_value):
    field_type = field_info["type"]
    field_id = field_info["field_id"]
    if field_type == "checkbox":
        checked_val = field_info["checked_value"]
        unchecked_val = field_info["unchecked_value"]
        if field_value != checked_val and field_value != unchecked_val:
            return f'ERROR: Invalid value "{field_value}" for checkbox field "{field_id}". The checked value is "{checked_val}" and the unchecked value is "{unchecked_val}"'
    elif field_type == "radio_group":
        option_values = [opt["value"] for opt in field_info["radio_options"]]
        if field_value not in option_values:
            return f'ERROR: Invalid value "{field_value}" for radio group field "{field_id}". Valid values are: {option_values}' 
    elif field_type == "choice":
        choice_values = [opt["value"] for opt in field_info["choice_options"]]
        if field_value not in choice_values:
            return f'ERROR: Invalid value "{field_value}" for choice field "{field_id}". Valid values are: {choice_values}'
    return None


def monkeypatch_pydpf_method():
    from pypdf.generic import DictionaryObject
    from pypdf.constants import FieldDictionaryAttributes

    original_get_inherited = DictionaryObject.get_inherited

    def patched_get_inherited(self, key: str, default = None):
        result = original_get_inherited(self, key, default)
        if key == FieldDictionaryAttributes.Opt:
            if isinstance(result, list) and all(isinstance(v, list) and len(v) == 2 for v in result):
                result = [r[0] for r in result]
        return result

    DictionaryObject.get_inherited = patched_get_inherited


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: fill_fillable_fields.py [input pdf] [field_values.json] [output pdf]")
        sys.exit(1)
    monkeypatch_pydpf_method()
    input_pdf = sys.argv[1]
    fields_json = sys.argv[2]
    output_pdf = sys.argv[3]
    try:
        fill_pdf_fields(input_pdf, fields_json, output_pdf)
    except (FileNotFoundError, PortablePathError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
