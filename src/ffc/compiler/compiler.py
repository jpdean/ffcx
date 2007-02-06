"""This is the compiler, acting as the main interface for compilation
of forms and breaking the compilation into several sequential phases,
each represented by a separate module:

   0. language        -  expressing the form in the form language
   1. analysis        -  simplifying and preprocessing the form
   2. representation  -  computing a representation of the form
   3. optimization    -  optimizing the form representation
   4. codegeneration  -  generating code according to a format
   5. format          -  writing the generated code to file

"""

__author__ = "Anders Logg (logg@simula.no)"
__date__ = "2007-02-05 -- 2007-02-05"
__copyright__ = "Copyright (C) 2007 Anders Logg"
__license__  = "GNU GPL Version 2"

# FFC common modules
from ffc.common.debug import *
from ffc.common.constants import *

# FFC compiler modules
import language
from analysis.checks import *
#from analysis.reassign import *
#import representation
#import optimization
#import codegeneration
#import format

def compile(form, name = "Form", output = FFC_LANGUAGE, options = FFC_OPTIONS):
    "Compile the given form for the given language."

    # Check that we get a Form
    if not isinstance(form, language.Form):
        raise RuntimeError, "Not a form: " + str(form)

    # Phase 1: analyze form
    form = analyze_form(form)

    # Phase 2: compute form representation
    compute_representation(form)

    # Phase 3: optimize form representation
    #optimization.compute_optimization(form)

    # Phase 4: generate code
    #codegeneration.generate_code(form)

    # Phase 5: format code
    #format.format_code(form)


def analyze_form(form):
    "Analyze form"

    debug("")
    debug("Compiler phase 1: Analyzing form")
    debug("--------------------------------")
    debug_indent()

    print form

    # Check validity of form
    check_form(form)

    # Reassign form indices
    reassign_indices(form)

    print form

    debug_indent(-1)
    
    return form

def compute_representation(form):
    "Compute form representation"

    debug("")
    debug("Compiler phase 2: Computing form representation")
    debug("-----------------------------------------------")
    debug_indent()
