PyDuino
=======

Intro
-----
A rudimentary Python-to-C++ converter for Arduino projects.

Usage
-----
Use chmod +x on parser.py, then run ./parser.py with test.py as argument

Known Limitations
=================
Partial list of limitations:

1. Very basic string variable support
1. No dictionary support, yet
1. Lists and tuples only work when all elements are of the same type
1. Using while loops does not work yet
1. Advanced operators like += / -= don't work
1. Boolean support is in its infancy
1. Handling `if __name__ == "__main__":`
1. Handling `str()`
1. Many more not known yet

Needed Tests
============
* Functions with default values
* More operator test
* String slices
