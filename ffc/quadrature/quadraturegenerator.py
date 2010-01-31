"Code generator for quadrature representation."

__author__ = "Kristian B. Oelgaard (k.b.oelgaard@gmail.com)"
__date__ = "2009-01-07"
__copyright__ = "Copyright (C) 2009-2010 Kristian B. Oelgaard"
__license__  = "GNU GPL version 3 or any later version"

# Last changed: 2010-01-25

# Python modules.
import numpy

# UFL modules.
from ufl.algorithms.printing import tree_format

## FFC modules.
from ffc.log import info, debug, ffc_assert
from ffc.cpp import tabulate_matrix, tabulate_vector
from ffc.cpp import IndentControl
from ffc.cpp import format
from ffc.cpp import remove_unused, choose_map

# Utility and optimisation functions for quadraturegenerator.
from quadraturegenerator_utils import generate_loop
from quadraturetransformer import QuadratureTransformer

from optimisedquadraturetransformer import QuadratureTransformerOpt
from symbolics import generate_aux_constants

def generate_integral_code(ir, prefix, options):
    "Generate code for integral from intermediate representation."

    # Generate code
    code = {}
    code["classname"] = format["classname " + ir["domain_type"] + "_integral"](prefix, ir["form_id"], ir["domain_id"])
    code["members"] = ""
    code["constructor"] = format["do nothing"]
    code["destructor"] = format["do nothing"]
    code["tabulate_tensor"] = _tabulate_tensor(ir, options)

    return code

def _tabulate_tensor(ir, options):
    "Generate code for a single integral (tabulate_tensor())."

    f_comment       = format["comment"]
    f_G             = format["geometry constant"]
    f_const_double  = format["const float declaration"]
    f_switch        = format["switch"]
    f_switch        = format["switch"]
    f_float         = format["float"]
    f_assign        = format["assign"]
    f_component     = format["component"]
    f_A             = format["element tensor quad"]
    f_r             = format["free indices"][0]

    # FIXME: KBO: Handle this in a better way, make -O option take an argument?
    if options["optimize"]:
        # These options results in fast code, but compiles slower and there
        # might still be bugs.
        optimise_options = {"non zero columns": True,
                            "ignore ones": True,
                            "remove zero terms": True,
                            "simplify expressions": True,
                            "ignore zero tables": True}
    else:
        # These options should be safe and fast, but result in slow code.
        optimise_options = {"non zero columns": False,
                            "ignore ones": False,
                            "remove zero terms": False,
                            "simplify expressions": False,
                            "ignore zero tables": False}

    # Common data and objects.
    domain_type         = ir["domain_type"]
    geometric_dimension = ir["geometric_dimension"]
    num_facets          = ir["num_facets"]
    integrals           = ir["integrals"]
    prim_idims          = ir["prim_idims"]
    Indent = IndentControl()

    # Create transformer.
    if optimise_options["simplify expressions"]:
        transformer = QuadratureTransformerOpt(ir, optimise_options, format)
    else:
        transformer = QuadratureTransformer(ir, optimise_options, format)

    operations = []
    if domain_type == "cell":
        # Update treansformer with facets and generate code + set of used geometry terms.
        transformer.update_facets(None, None)
        tensor_code, mem_code, num_ops = _generate_element_tensor(integrals, transformer, Indent, format)
        tensor_code = "\n".join(tensor_code)

        # Set operations equal to num_ops (for printing info on operations).
        operations.append(num_ops)

        # Get Jacobian snippet.
        # FIXME: This will most likely have to change if we support e.g., 2D elements in 3D space.
        jacobi_code = format["jacobian and inverse"](geometric_dimension)
        jacobi_code += "\n\n" + format["scale factor snippet"]

    elif domain_type == "exterior_facet":
        cases = [None for i in range(num_facets)]
        for i in range(num_facets):
            # Update treansformer with facets and generate case code + set of used geometry terms.
            transformer.update_facets(i, None)
            c, mem_code, ops = _generate_element_tensor(integrals, transformer, Indent, format)
            case = [f_comment("Total number of operations to compute element tensor (from this point): %d" % ops)]
            case += c
            cases[i] = "\n".join(case)

            # Save number of operations (for printing info on operations).
            operations.append((i, ops))

        # Generate tensor code for all cases using a switch.
        # FIXME: KBO: move 'facet' to format
        tensor_code = f_switch("facet", cases)

        # Get Jacobian snippet.
        # FIXME: This will most likely have to change if we support e.g., 2D elements in 3D space.
        jacobi_code = format["jacobian and inverse"](geometric_dimension)
        jacobi_code += "\n\n" + format["facet determinant"](geometric_dimension)
        jacobi_code += "\n\n" + format["generate normal"](geometric_dimension, domain_type)

    elif domain_type == "interior_facet":
        # Modify the dimensions of the primary indices because we have a macro element
        prim_idims = [d*2 for d in prim_idims]

        cases = [[None for j in range(num_facets)] for i in range(num_facets)]
        for i in range(num_facets):
            for j in range(num_facets):
                # Update treansformer with facets and generate case code + set of used geometry terms.
                transformer.update_facets(i, j)
                c, mem_code, ops = _generate_element_tensor(integrals, transformer, Indent, format, interior=True)
                case = [f_comment("Total number of operations to compute element tensor (from this point): %d" % ops)]
                case += c
                cases[i][j] = "\n".join(case)

                # Save number of operations (for printing info on operations).
                operations.append((i, j, ops))

        # Generate tensor code for all cases using a switch.
        # FIXME: KBO: move 'facet0' and 'facet1' to format
        tensor_code = f_switch("facet0", [f_switch("facet1", cases[i]) for i in range(len(cases))])

        # Get Jacobian snippet.
        # FIXME: This will most likely have to change if we support e.g., 2D elements in 3D space.
        map0 = choose_map["+"]
        map1 = choose_map["-"]
        jacobi_code  = format["jacobian and inverse"](geometric_dimension, map0)
        jacobi_code += "\n\n"
        jacobi_code += format["jacobian and inverse"](geometric_dimension, map1)
        jacobi_code += "\n\n"
        jacobi_code += format["facet determinant"](geometric_dimension, map0)
        jacobi_code += "\n\n" + format["generate normal"](geometric_dimension, domain_type)
    else:
        error("Unhandled integral type: " + str(integral_type))

    # After we have generated the element code for all facets we can remove
    # the unused transformations and tabulate the used psi tables and weights.
    common = [remove_unused(jacobi_code, transformer.trans_set)]
    common += _tabulate_weights(transformer, Indent, format)
    common += _tabulate_psis(transformer, Indent, format)

    # Reset the element tensor (array 'A' given as argument to tabulate_tensor() by assembler)
    # Handle functionals.
    value = f_float(0)
    if prim_idims == []:
        common += [f_assign(f_component(f_A, "0"), f_float(0))]
    else:
        dim = reduce(lambda v,u: v*u, prim_idims)
        common += generate_loop([f_assign(f_component(f_A, f_r), f_float(0))], [(f_r, 0, dim)], Indent, format)

    # Create the constant geometry declarations (only generated if simplify expressions are enabled).
    geo_ops, geo_code = generate_aux_constants(transformer.geo_consts, f_G, f_const_double)
    if geo_code:
        common += geo_code

    # Add comments.
    common += ["", f_comment("Compute element tensor using UFL quadrature representation")]
    common += [f_comment("Optimisations: %s" % ", ".join([str(i) for i in optimise_options.items()]))]

    # Print info on operation count
    message = {"cell": "Number of operations to compute tensor: %d",
               "exterior_facet": "Number of operations to compute tensor for facet %d: %d",
               "interior_facet": "Number of operations to compute tensor for facets (%d, %d): %d"}
    for ops in operations:
        info(message[domain_type] % ops)
    return "\n".join(common) + "\n" + tensor_code

def _generate_element_tensor(integrals, transformer, Indent, format, interior=False):
    "Construct quadrature code for element tensors."

    # Prefetch formats to speed up code generation.
    f_comment      = format["comment"]
    f_ip           = format["integration points"]

    # Initialise return values.
    element_code     = []
    tensor_ops_count = 0
    # TODO: KBO: The members_code was used when I generated the load_table.h
    # file which could load tables of basisfunction. This feature has not
    # been reimplemented. However, with the new design where we only
    # tabulate unique tables (and only non-zero entries) it doesn't seem to
    # be necessary. Should it be deleted?
    members_code = ""

    # We receive a dictionary {num_points: form,}.
    # Loop points and forms.
    for points, integral in integrals.items():

        debug("Looping points: " + str(points))
        debug("integral: " + str(integral))
        debug("\nIntegral tree_format: " + str(tree_format(integral)))

        ip_code = ["", Indent.indent(f_comment\
            ("Loop quadrature points for integral"))]

        # Update transformer to the current number of quadrature points.
        transformer.update_points(points)

        # Generate code and get number of operations
        integral_code, num_ops = transformer.generate_code(integral.integrand(), Indent, interior)

        # Get number of operations to compute entries for all terms when
        # looping over all IPs and update tensor count.
        num_operations = num_ops*points
        tensor_ops_count += num_operations

        ip_code.append(f_comment\
            ("Number of operations to compute element tensor for following IP loop = %d" %(num_operations)) )

        # Loop code over all IPs.
        if integral_code:
            if points > 1:
                ip_code += generate_loop(integral_code, [(f_ip, 0, points)], Indent, format)
            else:
                ip_code.append(f_comment("Only 1 integration point, omitting IP loop."))
                ip_code += integral_code

        # Add integration points code to element code.
        element_code += ip_code

    return (element_code, members_code, tensor_ops_count)

def _tabulate_weights(transformer, Indent, format):
    "Generate table of quadrature weights."

    # Prefetch formats to speed up code generation.
    f_float    = format["floating point"]
    f_table    = format["static const float declaration"]
    f_block    = format["block"]
    f_sep      = format["separator"]
    f_weight   = format["weight"]
    f_component =  format["component"]
    f_group    = format["grouping"]
    f_assign    = format["assign"]

    code = ["", Indent.indent(format["comment"]("Array of quadrature weights"))]

    # Loop tables of weights and create code.
    for num_points in transformer.used_weights:
        weights, points = transformer.quadrature_weights[num_points]

        # FIXME: For now, raise error if we don't have weights.
        # We might want to change this later.
        ffc_assert(weights.any(), "No weights.")

        # Create name and value for weight.
        name = f_table + f_weight(num_points)
        value = f_float(weights[0])
        if len(weights) > 1:
            name += f_component("", str(num_points))
            value = tabulate_vector(weights, format)
        code += [f_assign(Indent.indent(name), value)]

        # Tabulate the quadrature points (uncomment for different options).
        # 1) Tabulate the points as: p0, p1, p2, with p0 = (x0, y0, z0) etc.
        # Use f_float to format the value (enable variable precision).
        formatted_points = [f_group(f_sep.join([f_float(val)\
                            for val in point])) for point in points]

        # Create comment.
        comment = "Quadrature points on the UFC reference element: " \
                  + f_sep.join(formatted_points)
        code += [Indent.indent(format["comment"](comment))]

        # 2) Tabulate the coordinates of the points p0, p1, p2 etc.
        #    X: x0, x1, x2
        #    Y: y0, y1, y2
        #    Z: z0, z1, z2
#            comment = "Quadrature coordinates on the UFC reference element: "
#            code += [Indent.indent(format["comment"](comment))]

#            # All points have the same number of coordinates.
#            num_coord = len(points[0])

#            # All points have x-coordinates.
#            xs = [f_float(p[0]) for p in points]
#            comment = "X: " + f_sep.join(xs)
#            code += [Indent.indent(format["comment"](comment))]

#            ys = []
#            zs = []
#            # Tabulate y-coordinate if we have 2 or more coordinates.
#            if num_coord >= 2:
#                ys = [f_float(p[1]) for p in points]
#                comment = "Y: " + f_sep.join(ys)
#                code += [Indent.indent(format["comment"](comment))]
#            # Only tabulate z-coordinate if we have 3 coordinates.
#            if num_coord == 3:
#                zs = [f_float(p[2]) for p in points]
#                comment = "Z: " + f_sep.join(zs)
#                code += [Indent.indent(format["comment"](comment))]

        code += [""]

    return code

def _tabulate_psis(transformer, Indent, format):
    "Tabulate values of basis functions and their derivatives at quadrature points."

    # Prefetch formats to speed up code generation.
    f_comment    = format["comment"]
    f_block      = format["block"]
    f_table      = format["static const float declaration"]
    f_component  = format["component"]
    f_const_uint = format["static const uint declaration"]
    f_nzcolumns  = format["nonzero columns"]
    f_sep        = format["separator"]
    f_assign    = format["assign"]

    # FIXME: Check if we can simplify the tabulation

    code = []
    code += [Indent.indent(f_comment("Value of basis functions at quadrature points.") )]

    inv_name_map = transformer.name_map
    tables = transformer.unique_tables

    # Get list of non zero columns, if we ignore ones ignore columns with one component.
    if transformer.optimise_options["ignore ones"]:
        nzcs = [val[1] for key, val in inv_name_map.items()\
                                        if val[1] and len(val[1][1]) > 1]
    else:
        nzcs = [val[1] for key, val in inv_name_map.items()\
                                        if val[1]]

    # TODO: Do we get arrays that are not unique?
    new_nzcs = []
    for nz in nzcs:
        # Only get unique arrays.
        if not nz in new_nzcs:
            new_nzcs.append(nz)

    # Construct name map.
    name_map = {}
    if inv_name_map:
        for name in inv_name_map:
            if inv_name_map[name][0] in name_map:
                name_map[inv_name_map[name][0]].append(name)
            else:
                name_map[inv_name_map[name][0]] = [name]

    # Loop items in table and tabulate.
    for name in sorted(list(transformer.used_psi_tables)):
        # Only proceed if values are still used (if they're not remapped).
        vals = tables[name]
        if not vals is None:
            # Add declaration to name.
            ip, dofs = numpy.shape(vals)
            decl_name = f_component(f_table + name, [ip, dofs])

            # Generate array of values.
            value = tabulate_matrix(vals, format)
            code += [f_assign(Indent.indent(decl_name), Indent.indent(value)), ""]

        # Tabulate non-zero indices.
        if transformer.optimise_options["non zero columns"]:
            if name in name_map:
                for n in name_map[name]:
                    if inv_name_map[n][1] and inv_name_map[n][1] in new_nzcs:
                        i, cols = inv_name_map[n][1]
                        if not i in transformer.used_nzcs:
                            continue
                        code += [Indent.indent(f_comment("Array of non-zero columns") )]
                        value = f_block(f_sep.join(["%d" %c for c in list(cols)]))
                        name_col = f_component(f_const_uint + f_nzcolumns(i), len(cols))
                        code += [f_assign(Indent.indent(name_col), value), ""]

                        # Remove from list of columns.
                        new_nzcs.remove(inv_name_map[n][1])
    return code