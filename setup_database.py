from pathlib import Path


def main():
    schema_path = Path(__file__).with_name("supabase_schema.sql")
    print(schema_path.read_text(encoding="utf-8"))
    print("\nPaste this SQL into Supabase SQL Editor and run it once.")


if __name__ == "__main__":
    main()
