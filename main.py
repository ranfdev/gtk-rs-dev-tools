#!/usr/bin/python3

import os
import sys
import argparse
import re
import logging
import gi
gi.require_version('GIRepository', '2.0')
gi.require_version('GObject', '2.0')
from gi.repository import GIRepository, GObject
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum, auto

@dataclass
class Property:
    name: str
    rust_type: str
    default_value: str
    nullable: bool = False
    doc: Optional[str] = None

@dataclass
class Signal:
    name: str
    params: List[Tuple[str, str]]  # List of (param_name, param_type)
    return_type: Optional[str] = None

class RustGObjectGenerator:
    VALID_IDENTIFIER = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*$')
    VALID_CLASSNAME = re.compile(r'^[A-Z][A-Za-z0-9]*$')
    
    TYPE_MAPPING = {
        'string': 'String',
        'str': 'String',
        'i32': 'i32',
        'u32': 'u32',
        'i64': 'i64',
        'u64': 'u64',
        'f32': 'f32',
        'f64': 'f64',
        'bool': 'bool',
        'boolean': 'bool',
        'object': 'glib::Object',
    }

    def __init__(self):
        self.imp_template = '''// Generated by RustGObjectGenerator
// This file is licensed under the same terms as the project it belongs to

use gtk::{{glib, prelude::*, subclass::prelude::*}};
use adw::subclass::prelude::*;
use glib::subclass::Signal;
use glib::Properties;
use std::cell::RefCell;
use std::sync::OnceLock;
{additional_imports}

mod imp {{
    use super::*;

    #[derive(Properties, Default, gtk::CompositeTemplate)]
    #[properties(wrapper_type = super::{class_name})]
    #[template(file = "{template_file}")]
    pub struct {class_name} {{
{properties}
{template_children}
    }}

    #[glib::derived_properties]
    impl ObjectImpl for {class_name} {{
        fn constructed(&self) {{
            self.parent_constructed();
            let obj = self.obj();
            // Initialize default state here if needed
        }}

        fn signals() -> &'static [Signal] {{
            static SIGNALS: OnceLock<Vec<Signal>> = OnceLock::new();
            SIGNALS.get_or_init(|| vec![
{signals}
            ])
        }}
    }}

    #[glib::object_subclass]
    impl ObjectSubclass for {class_name} {{
        const NAME: &'static str = "{class_name}";
        type Type = super::{class_name};
        type ParentType = {parent_class};

        fn class_init(klass: &mut Self::Class) {{
            klass.bind_template();
            klass.bind_template_callbacks();
        }}

        fn instance_init(obj: &glib::subclass::InitializingObject<Self>) {{
            obj.init_template();
        }}
    }}

    impl WidgetImpl for {class_name} {{
        fn size_allocate(&self, width: i32, height: i32, baseline: i32) {{
            self.parent_size_allocate(width, height, baseline);
        }}

        fn snapshot(&self, snapshot: &gtk::Snapshot) {{
            self.parent_snapshot(snapshot);
        }}
    }}

    // Generate Impl blocks for each parent class
    {parent_impls}

    #[gtk::template_callbacks]
    impl {class_name} {{
{template_callbacks}
    }}
}}

glib::wrapper! {{
    pub struct {class_name}(ObjectSubclass<imp::{class_name}>)
        @extends {parent_hierarchy},
        @implements gtk::Accessible, gtk::Buildable, gtk::ConstraintTarget;
}}

impl {class_name} {{
    pub fn new() -> Self {{
        glib::Object::new()
    }}

    pub fn new_with_params({constructor_params}) -> Self {{
        glib::Object::builder()
{property_builders}
            .build()
    }}

{additional_methods}
}}
'''

    def validate_class_name(self, name: str) -> bool:
        """Validate class name follows Rust naming conventions."""
        return bool(self.VALID_CLASSNAME.match(name))

    def validate_identifier(self, name: str) -> bool:
        """Validate identifier follows Rust naming conventions."""
        return bool(self.VALID_IDENTIFIER.match(name))

    def parse_property(self, prop_str: str) -> Property:
        """Parse property string into Property object with validation."""
        try:
            # Handle optional documentation
            if '#' in prop_str:
                prop_str, doc = prop_str.split('#', 1)
                doc = doc.strip()
            else:
                doc = None

            # Split name and type
            if ':' not in prop_str:
                raise ValueError("Property must be in format 'name:type'")
                
            name, type_str = prop_str.split(':', 1)
            name = name.strip()
            type_str = type_str.strip()
            
            if not self.validate_identifier(name):
                raise ValueError(f"Invalid property name: {name}")
            
            # Handle nullable types
            nullable = type_str.endswith('?')
            if nullable:
                type_str = type_str[:-1]
            
            # Handle custom types
            if type_str.lower() not in self.TYPE_MAPPING:
                # Assume it's a custom type
                return Property(
                    name=name,
                    prop_type=PropertyType.CUSTOM,
                    rust_type=type_str,
                    default_value='None' if nullable else f'{type_str}::default()',
                    nullable=nullable,
                    doc=doc
                )
            
            # Handle built-in types
            type_str = type_str.lower()
            rust_type = self.TYPE_MAPPING[type_str]
            
            if nullable:
                rust_type = f'Option<{rust_type}>'
            
            return Property(
                name=name,
                rust_type=rust_type,
                default_value='None' if nullable else f'{rust_type}::default()',
                nullable=nullable,
                doc=doc
            )
            
        except ValueError as e:
            raise ValueError(f"Invalid property format. Expected 'name:type[?] #doc', got '{prop_str}'. {str(e)}")

    def parse_signal(self, signal_str: str) -> Signal:
        """Parse signal string into Signal object with validation."""
        try:
            # Handle return type if present
            if '->' in signal_str:
                signal_str, return_type = signal_str.split('->', 1)
                return_type = return_type.strip()
            else:
                return_type = None

            # Handle parameters if present
            if '(' in signal_str:
                name, params_str = signal_str.split('(', 1)
                params_str = params_str.rstrip(')')
                name = name.strip()
                params = []
                
                if params_str:
                    for param in params_str.split(','):
                        param = param.strip()
                        if not param:
                            continue
                        if ':' in param:
                            param_name, param_type = param.split(':', 1)
                            param_name = param_name.strip()
                            param_type = param_type.strip()
                            if not self.validate_identifier(param_name):
                                raise ValueError(f"Invalid parameter name: {param_name}")
                            params.append((param_name, param_type))
                        else:
                            raise ValueError(f"Invalid parameter format: {param}")
            else:
                name = signal_str.strip()
                params = []

            # Validate the Rust method name (after converting hyphens)
            rust_method_name = name.replace('-', '_')
            if not self.validate_identifier(rust_method_name):
                raise ValueError(f"Invalid signal name (after converting hyphens): {name}")
                
            return Signal(name=name, params=params, return_type=return_type)
                
        except ValueError as e:
            raise ValueError(f"Invalid signal format. Expected 'name(param:type,...) -> return_type' or 'name', got '{signal_str}'. {str(e)}")

    def generate_properties_code(self, properties: List[Property]) -> str:
        """Generate Rust code for properties."""
        prop_lines = []
        for prop in properties:
            # Add documentation if present
            if prop.doc:
                prop_lines.append(f'        /// {prop.doc}')
            
            # Handle different property types
            if prop.nullable:
                # For nullable types, we wrap in Option<T> once
                prop_lines.append(f'        #[property(get, set, nullable)]\n        {prop.name}: RefCell<{prop.rust_type}>,')
            elif prop.prop_type == PropertyType.OBJECT:
                # For object types, we wrap in Option<T> since they're nullable by default
                prop_lines.append(f'        #[property(get, set)]\n        {prop.name}: RefCell<Option<{prop.rust_type}>>,')
            else:
                # For non-nullable types
                prop_lines.append(f'        #[property(get, set)]\n        {prop.name}: RefCell<{prop.rust_type}>,')
        
        return '\n'.join(prop_lines) if prop_lines else '        // No properties defined'

    def generate_signals_code(self, signals: List[Signal]) -> str:
        """Generate Rust code for signals."""
        signal_lines = []
        for signal in signals:
            builder = f'Signal::builder("{signal.name}")'
            
            if signal.params:
                # Generate static_type() calls for each parameter type
                params_str = ', '.join(
                    f'{type_}::static_type()'
                    for _, type_ in signal.params
                )
                builder += f'\n                    .param_types([{params_str}])'
            
            if signal.return_type:
                builder += f'\n                    .return_type::<{signal.return_type}>()'
            
            builder += '\n                    .build(),'
            signal_lines.append(builder)
            
        return '\n'.join(signal_lines) if signal_lines else '                // No signals defined'

    def generate_template_children(self, children: List[str]) -> str:
        """Generate template children code."""
        if not children:
            return "        // No template children defined"
            
        lines = []
        for child in children:
            # Split on first colon only to handle Rust-style types
            if ':' not in child:
                raise ValueError(f"Template child must be in format 'name:type', got '{child}'")
                
            first_colon = child.find(':')
            name = child[:first_colon].strip()
            type_ = child[first_colon+1:].strip()
            
            # Validate the name
            if not self.validate_identifier(name):
                raise ValueError(f"Invalid template child name: {name}")
            lines.append(f'        #[template_child]\n        pub {name}: TemplateChild<{type_}>,')

        return '\n'.join(lines)

    def generate_template_callbacks(self, callbacks: List[str]) -> str:
        """Generate template callback methods with signal-like syntax."""
        if not callbacks:
            return "        // No template callbacks defined"
            
        lines = []
        for callback in callbacks:
            try:
                # Parse using the same logic as signals
                signal = self.parse_signal(callback)
                
                # Build parameter string
                params_str = ', '.join(f'{name}: {type_}' for name, type_ in signal.params)
                
                # Build return type
                return_type = f' -> {signal.return_type}' if signal.return_type else ''
                
                # Build method body
                method_body = f'fn {signal.name}(&self, {params_str}){return_type} {{\n'
                method_body += '        // TODO: Implement callback\n'
                method_body += '    }'
                
                lines.append(f'        #[template_callback]\n        {method_body}')
                
            except ValueError as e:
                # Fall back to simple callback if parsing fails
                lines.append(f'        #[template_callback]\n        {callback}')
            
        return '\n'.join(lines)

    def generate_additional_methods(self, properties: List[Property], signals: List[Signal]) -> str:
        """Generate additional helper methods."""
        methods = []
        
        # Generate signal emission methods
        for signal in signals:
            params_str = ', '.join(f'{name}: {type_}' for name, type_ in signal.params)
            # Convert hyphens to underscores in method name
            rust_method_name = signal.name.replace('-', '_')
            method_name = f"emit_{rust_method_name}"
            if params_str:
                methods.append(f'''    pub fn {method_name}(&self, {params_str}) {{
        self.emit_by_name::<()>("{signal.name}", &[{', '.join(f'&{n}' for n, _ in signal.params)}]);
    }}''')
            else:
                methods.append(f'''    pub fn {method_name}(&self) {{
        self.emit_by_name::<()>("{signal.name}", &[]);
    }}''')

        # Generate signal connection methods
        for signal in signals:
            # Build closure parameter types (without names)
            param_types = [type_ for _, type_ in signal.params]
            
            # Add return type if present
            return_type = signal.return_type or '()'
            
            # Build closure type
            closure_type = f'Fn({", ".join(param_types)}) -> {return_type} + \'static'
            
            # Build method signature
            param_lines = []
            if signal.params:
                param_lines.append('let obj = values[0].get::<Self>().expect("Failed to get self from values");')
                param_lines.extend(
                    f'let {name} = values[{i+1}].get::<{type_}>().expect("Failed to get parameter {name}");'
                    for i, (name, type_) in enumerate(signal.params)
                )
            
            # Convert hyphens to underscores in method name
            rust_method_name = signal.name.replace('-', '_')
            methods.append(f'''    pub fn connect_{rust_method_name}<F: {closure_type}>(&self, f: F) -> glib::SignalHandlerId {{
        self.connect_local("{signal.name}", false, move |values| {{
            {''.join(f'{line}\n            ' for line in param_lines)}
            {f'let result = f({", ".join(name for name, _ in signal.params)});' if return_type != '()' else f'f({", ".join(name for name, _ in signal.params)});'}
            {f'Some(result.to_value())' if return_type != '()' else 'None'}
        }})
    }}''')

        return '\n\n'.join(methods)

    def print_widget_hierarchy(self, widget, indent=0):
        """
        Print the complete class hierarchy of a GTK widget using GObject introspection.
        
        Args:
            widget: A GTK widget or GType
            indent: Current indentation level (used recursively)
        """
        if isinstance(widget, GObject.GType):
            current_type = widget
        else:
            current_type = widget.get_type()
        
        # Get the name of the current class
        type_name = current_type.name
        
        # Print the current class with proper indentation
        print("  " * indent + f"└─ {type_name}")
        
        # Get parent type
        parent_type = current_type.parent
        
        # Recursively print parent classes until we reach GObject
        if parent_type and parent_type.name != "GObject":
            self.print_widget_hierarchy(parent_type, indent + 1)

    def get_widget_hierarchy_list(self, info):
        """
        Return a list of class names in the widget's hierarchy.
        
        Args:
            info: A GIRepository.BaseInfo object
        
        Returns:
            list: List of class names in inheritance order
        """
        hierarchy = []
        current_info = info
        
        while current_info:
            # Get the namespace and name
            namespace = current_info.get_namespace()
            name = current_info.get_name()
            
            if namespace and name:
                hierarchy.append(f"{namespace}.{name}")
            
            # Get parent info
            try:
                parent_type = current_info.get_parent()
                if not parent_type:
                    break
                    
                current_info = GIRepository.Repository.get_default().find_by_name(
                    parent_type.get_namespace(),
                    parent_type.get_name()
                )
            except Exception as e:
                logging.debug(f"Error getting parent info: {str(e)}")
                break
                
        return hierarchy

    def get_parent_hierarchy(self, parent_class: str) -> List[str]:
        """Get the full parent hierarchy using the simpler hierarchy function."""
        logger = logging.getLogger(__name__)
        
        def hierarchy(cls, parents = []):
            """Recursively get all parent classes until InitiallyUnowned."""
            if cls == GObject.GInterface:
                return False
            if cls == GObject.InitiallyUnowned:
                return True
            parents.append(cls)
            for b in cls.__bases__:
                if hierarchy(b, parents):
                    return True
            parents.pop()
            return False

        try:
            # Require GTK 4.0 before importing
            gi.require_version('Gtk', '4.0')
            from gi.repository import GObject
            
            # Convert Rust-style type names to Python module paths
            if '::' in parent_class:
                module, classname = parent_class.split('::', 1)
                # Map Rust module names to Python modules
                module_map = {
                    'gtk': 'Gtk',
                    'glib': 'GLib',
                    'gio': 'Gio',
                    'gdk': 'Gdk',
                    'gdk4': 'Gdk',
                    'gsk': 'Gsk',
                    'pango': 'Pango',
                    'cairo': 'cairo',
                    'adw': 'Adw',
                }
                module = module_map.get(module.lower(), module)
                import_path = f"gi.repository.{module}"
            else:
                # Try common GTK modules
                import_path = f"gi.repository.{parent_class.split('.')[0]}"
                classname = parent_class.split('.')[-1]

            # Import the module and get the class
            module = __import__(import_path, fromlist=[classname])
            widget_class = getattr(module, classname)
            
            # Get the hierarchy using the new function
            parents = []
            hierarchy(widget_class, parents)
            
            # Convert to Rust-style module::Class format and remove duplicates
            rust_hierarchy = []
            seen = set()
            for cls in parents:
                module_name = cls.__module__.split('.')[-1].lower()
                if module_name == 'gtk':
                    rust_class = f"gtk::{cls.__name__}"
                elif module_name == 'gobject':
                    rust_class = f"glib::{cls.__name__}"
                else:
                    rust_class = f"{module_name}::{cls.__name__}"
                
                if rust_class not in seen:
                    rust_hierarchy.append(rust_class)
                    seen.add(rust_class)
            
            logger.debug(f"Generated hierarchy for {parent_class}: {rust_hierarchy}")
            return rust_hierarchy
            
        except Exception as e:
            logger.error(f"Error getting hierarchy for {parent_class}: {str(e)}")
            logger.debug("Full exception:", exc_info=True)
            return [parent_class]

    def generate_code(self, class_name: str, parent_class: str, 
                     properties: List[str], signals: List[str], 
                     template_file: Optional[str] = None,
                     template_children: Optional[List[str]] = None,
                     template_callbacks: Optional[List[str]] = None,
                     additional_imports: Optional[List[str]] = None) -> str:
        """Generate complete Rust code for the GObject class."""
        try:
            logging.basicConfig(level=logging.DEBUG)
            logger = logging.getLogger(__name__)
            
            if not self.validate_class_name(class_name):
                raise ValueError(f"Invalid class name: {class_name}")

            # Parse properties and signals
            parsed_properties = [self.parse_property(prop) for prop in properties]
            parsed_signals = [self.parse_signal(signal) for signal in signals]

            # Handle template file path
            logger.debug(f"Original template_file: {template_file}")
            template_path = template_file.replace('\\', '\\\\') if template_file else ""
            logger.debug(f"Processed template_path: {template_path}")

            # Generate parent hierarchy string
            parent_hierarchy = ', '.join(filter(None, self.get_parent_hierarchy(parent_class)))
            
            # Log all format parameters
            format_params = {
                'class_name': class_name,
                'parent_class': parent_class,
                'parent_hierarchy': parent_hierarchy,
                'additional_imports': '\n'.join(additional_imports or []),
                'template_file': template_path if template_path else "",
                'template_children': self.generate_template_children(template_children or []),
                'template_callbacks': self.generate_template_callbacks(template_callbacks or []),
                'properties': self.generate_properties_code(parsed_properties),
                'signals': self.generate_signals_code(parsed_signals),
                'constructor_params': self.generate_constructor_params(parsed_properties),
                'property_builders': self.generate_property_builders(parsed_properties),
                'additional_methods': self.generate_additional_methods(parsed_properties, parsed_signals),
                'parent_impls': self.generate_parent_impls(self.get_parent_hierarchy(parent_class), class_name)
            }
            
            logger.debug("Format parameters:")
            for key, value in format_params.items():
                logger.debug(f"{key}: {value}")

            # Generate the code
            return self.imp_template.format(
                class_name=class_name,
                parent_class=parent_class,
                parent_hierarchy=parent_hierarchy,
                additional_imports='\n'.join(additional_imports or []),
                template_file=template_path if template_path else "",
                template_children=self.generate_template_children(template_children or []),
                template_callbacks=self.generate_template_callbacks(template_callbacks or []),
                properties=self.generate_properties_code(parsed_properties),
                signals=self.generate_signals_code(parsed_signals),
                constructor_params=self.generate_constructor_params(parsed_properties),
                property_builders=self.generate_property_builders(parsed_properties),
                additional_methods=self.generate_additional_methods(parsed_properties, parsed_signals),
                parent_impls=self.generate_parent_impls(self.get_parent_hierarchy(parent_class), class_name)
            )
        except Exception as e:
            raise RuntimeError(f"Error generating code: {str(e)}")


    def generate_constructor_params(self, properties: List[Property]) -> str:
        return ', '.join(f'{p.name}: {p.rust_type}' for p in properties)

    def generate_property_builders(self, properties: List[Property]) -> str:
        return '\n'.join(f'            .property("{p.name}", {p.name})' 
                        for p in properties)

    def generate_parent_impls(self, parent_hierarchy: List[str], class_name: str) -> str:
        """Generate Impl blocks for each parent class in the hierarchy.
        
        Args:
            parent_hierarchy: List of parent classes in Rust format (e.g. ["gtk::Widget"])
            class_name: The name of the class being generated
        """
        impls = []
        for parent in parent_hierarchy:
            if parent == "gtk::Widget":
                continue  # Already handled by WidgetImpl
            
            # Extract the type name without module
            type_name = parent.split('::')[-1]
            
            impl = f'''    impl {type_name}Impl for {class_name} {{
        // Default implementations that forward to parent
    }}'''
            impls.append(impl)
        
        return '\n\n'.join(impls)

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    parser = argparse.ArgumentParser(description='Create a new GObject class in Rust')
    parser.add_argument('class_name', help='The class name in PascalCase')
    parser.add_argument('parent_class', help='The parent class name')
    parser.add_argument('--properties', nargs='*', help='Properties in format name:type', default=[])
    parser.add_argument('--signals', nargs='*', help='Signal names, optionally with parameters: name(param:type)', default=[])
    parser.add_argument('--imports', nargs='*', help='Additional imports', default=[])
    parser.add_argument('--template', help='Path to template UI file', default=None)
    parser.add_argument('--template-children', nargs='*', 
                       help='Template children in format name:type', default=[])
    parser.add_argument('--template-callbacks', nargs='*',
                       help='Template callback methods', default=[])
    parser.add_argument('path', help='Output path for the Rust file')
    
    args = parser.parse_args()

    try:
        # Create generator instance
        generator = RustGObjectGenerator()
        logger.debug(f"Generating code for class: {args.class_name}")
        logger.debug(f"Parent class: {args.parent_class}")
        logger.debug(f"Properties: {args.properties}")
        logger.debug(f"Signals: {args.signals}")
        logger.debug(f"Template file: {args.template}")
        logger.debug(f"Template children: {args.template_children}")
        logger.debug(f"Template callbacks: {args.template_callbacks}")
        logger.debug(f"Additional imports: {args.imports}")

        # Generate the code
        rust_code = generator.generate_code(
            class_name=args.class_name,
            parent_class=args.parent_class,
            properties=args.properties,
            signals=args.signals,
            template_file=args.template,
            template_children=args.template_children,
            template_callbacks=args.template_callbacks,
            additional_imports=args.imports
        )

        # Ensure output directory exists
        os.makedirs(args.path, exist_ok=True)
        
        # Write to file
        output_path = os.path.join(args.path, f"{args.class_name.lower()}.rs")
        with open(output_path, 'w') as f:
            f.write(rust_code)
            
        print(f"Successfully generated {output_path}")
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
