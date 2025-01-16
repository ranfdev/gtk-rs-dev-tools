# Rust GObject Generator

A Python script to generate Rust code for GTK/GObject-based widgets with support for properties, signals, and template UI files.

## Features

- Generates Rust code for custom GTK widgets
- Supports properties with various types (string, int, float, bool, object)
- Handles signals with parameters and return types
- Integrates with GTK template UI files
- Supports template children and callbacks
- Generates proper parent class hierarchy
- Includes libadwaita support
- Produces well-documented Rust code

## Usage

1. Install dependencies:
   ```bash
   sudo dnf install python3-gobject gtk4-devel
   ```

2. Run the generator:
   ```bash
   ./main.py MyWidget gtk::Widget \
       --properties "label:string" "count:i32" \
       --signals "clicked" "value-changed(new_value:i32)" \
       --template my_widget.ui \
       --template-children "button:gtk::Button" \
       --template-callbacks "on_button_clicked" \
       output_dir/
   ```

## Command Line Arguments

| Argument             | Description                                      |
|----------------------|--------------------------------------------------|
| `class_name`         | Name of the widget class (PascalCase)           |
| `parent_class`       | Parent class (e.g. `gtk::Widget`)               |
| `--properties`       | List of properties in `name:type` format        |
| `--signals`          | List of signals with optional parameters        |
| `--template`         | Path to template UI file                        |
| `--template-children`| List of template children in `name:type` format |
| `--template-callbacks| List of template callback methods              |
| `--imports`          | Additional Rust imports                         |
| `path`               | Output directory for generated files            |

## License

MIT License - See LICENSE file for details
