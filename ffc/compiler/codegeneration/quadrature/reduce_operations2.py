"Some simple functions for manipulating expressions symbolically"

__author__ = "Kristian B. Oelgaard (k.b.oelgaard@tudelft.nl)"
__date__ = "2009-03-04 -- 2009-03-18"
__copyright__ = "Copyright (C) 2009 Kristian B. Oelgaard"
__license__  = "GNU GPL version 3 or any later version"

# FFC common modules
from ffc.common.log import debug, error
from copy import deepcopy

BASIS = 0
IP  = 1
GEO = 2
CONST = 3
type_to_string = {BASIS:"basis", IP:"ip",GEO:"geo", CONST:"const"}

def generate_aux_constants(constant_decl, name, var_type, print_ops, format):
    "A helper tool to generate code for constant declarations"
    code = []
    append = code.append
    ops = 0
    sorted_list = [(v, k) for k, v in constant_decl.iteritems()]
    sorted_list.sort()
    for s in sorted_list:
        c = s[1].expand().reduce_ops()
        ops += c.ops()
        if print_ops:
            append(format["comment"]("Number of operations: %d" %c.ops()))
            append((var_type + name + str(s[0]), str(c)))
            append("")
        else:
            append((var_type + name + str(s[0]), str(c)))
    return (ops, code)

def optimise_code(expr, ip_consts, geo_consts, trans_set, format):
    """Optimise a given expression with respect to, basis functions,
    integration points variables and geometric constants.
    The function will update the dictionaries ip_const and geo_consts with new
    declarations and update the trans_set (used transformations)."""

    format_G  = format["geometry tensor"]
    format_ip = format["integration points"]

    # Return constant symbol if value is zero
    if expr.c == 0:
        return Symbol("", 0, CONST, format)

    # Reduce expression with respect to basis function variable
#    print "\nEXP: ", expr.remove_nested()
    expr = expr.expand()
#    print "\nEXP1: ", expr
    basis_expressions = expr.reduce_vartype(BASIS)

    # If we had a product instance we'll get a tuple back so embed in list
    if not isinstance(basis_expressions, list):
        basis_expressions = [basis_expressions]

    basis_vals = []
    # Process each instance of basis functions
    for b in basis_expressions:
        # Get the basis and the ip expression
        basis, ip_expr = b
#        print "\nbasis: ", basis
#        print "\nip_expr: ", ip_expr
        debug("basis\n" + str(basis))
        debug("ip_epxr\n" + str(ip_expr))

        # If we have no basis (like functionals) create a const
        if not basis:
            basis = Symbol("", 1, CONST, format)

        # If the ip expression doesn't contain any operations skip remainder
        if not ip_expr:
            basis_vals.append(basis)
            continue
        if not ip_expr.ops() > 0:
            basis_vals.append(Product([basis, ip_expr], format, True))
            continue

        # Reduce the ip expressions with respect to IP variables
        ip_expr = ip_expr.expand()
        ip_expressions = ip_expr.reduce_vartype(IP)
        debug("ip_epxressions\n" + str(ip_expressions))

        # If we had a product instance we'll get a tuple back so embed in list
        if not isinstance(ip_expressions, list):
            ip_expressions = [ip_expressions]

        ip_vals = []
        # Loop ip expressions
        for ip in ip_expressions:
            ip_dec, geo = ip
            debug("ip_dec: " + str(ip_dec))
            debug("geo: " + str(geo))
#            print "ip_dec: ", ip_dec
#            print "geo: ", geo
            # Update transformation set with those values that might be
            # embedded in IP terms
            if ip_dec:
                trans_set.update(map(lambda x: str(x), ip_dec.get_unique_vars(GEO)))

            # Append and continue if we did not have any geo values
            if not geo:
                ip_vals.append(ip_dec)
                continue

            # Update the transformation set with the variables in the geo term
            trans_set.update(map(lambda x: str(x), geo.get_unique_vars(GEO)))

#            print "RD"
            test = geo
            # Reduce operations of the geo term
            geo = geo.expand().reduce_ops()
#            if not test.expand() == geo.expand():
#                print "geo:\n", geo.expand()
#                print "test:\n", test
#                error("not equal")

            # Only declare auxiliary geo terms if we can save operations            
            if geo.ops() > 0:
                debug("\n\ngeo: " + str(geo))
                # If the geo term is not in the dictionary append it
                if not geo_consts.has_key(geo):
                    geo_consts[geo] = len(geo_consts)

                # Substitute geometry expression
                geo = Symbol(format_G + str(geo_consts[geo]), 1, GEO, format)

            # If we did not have any ip_declarations use geo, else create a
            # product and append to the list of ip_values
            if not ip_dec:
                ip_dec = geo
            else:
                ip_dec = Product([ip_dec, geo], format, True)
            ip_vals.append(ip_dec)

        # Create sum of ip expressions to multiply by basis
        if len(ip_vals) > 1:
            ip_expr = Sum(ip_vals, format, True)
        elif ip_vals:
            ip_expr = ip_vals.pop()

        # If we can save operations by declaring it as a constant do so, if it
        # is not in IP dictionary, add it and use new name
        if ip_expr.ops() > 0:
            if not ip_expr in ip_consts:
                ip_consts[ip_expr] = len(ip_consts)

            # Substitute ip expression
            ip_expr = Symbol(format_G + format_ip + str(ip_consts[ip_expr]), 1, IP, format)

        # Multiply by basis and append to basis vals
        basis_vals.append(Product([basis, ip_expr], format, True).expand())

    # Return sum of basis values
    return Sum(basis_vals, format, True)


class Symbol(object):
    def __init__(self, variable, count, symbol_type, format):
        """Initialise a Symbols object it contains a:
        v - string, variable name
        c - float, a count of number of occurrences
        t - Type, one of CONST, GEO, IP, BASIS"""

        # Save format TODO: Is it possible to define this once outside the
        # classes so that we don't have to 'drag' the format around?
        self.format = format

        self.v = variable
        self.c = float(count)
        self.t = symbol_type

        # Needed for symbols like std::cos(x*y + z) --> base_ops = 2
        # (should that really be 3?)
        # This variable should be set after construction
        # TODO: put this in the constructor
        self.base_expr = None
        self.base_op = 0

    def __repr__(self):
        "Representation for debugging"

        s = self.v + self.format["block"](type_to_string[self.t])
        # If a symbols is not a const we only need the count if it is different
        # from 1 and -1
        if self.t != CONST:
            if self.c != 1 and self.c != -1:
                s = self.format["multiply"]([self.format["floating point"](abs(self.c)), s])
        # If a symbol is a const, its representation is simply the count
        else:
            s += self.format["floating point"](abs(self.c))
        # Add a minus sign if needed
        if self.c < 0:
            s = self.format["subtract"](["", s])
        return s

    def __str__(self):
        "Simple string representation"

        # If the count is zero, there's no need to spend more time on it
        if self.c == 0:
            return self.format["floating point"](0.0)

        # If a symbols is not a const we only need the count if it is different
        # from 1 and -1
        if self.t != CONST:
            s = self.v
            if self.c != 1 and self.c != -1:
                s = self.format["multiply"]([self.format["floating point"](abs(self.c)), s])
        # If a symbol is a const, its representation is simply the count
        else:
            s = self.format["floating point"](abs(self.c))
        # Add a minus sign if needed
        if self.c < 0:
            s = self.format["subtract"](["", s])
        return s

    def __hash__(self):
        return hash(str(self))

    def __mul__(self, other):
        # If product will be zero
        if self.c == 0 or not other or other.c == 0:
            return Symbol("", 0, CONST, self.format)

        # Just handle multiplication by other symbols, else let other classes
        # handle it
        if isinstance(other, Symbol):
            return Product([self, other], self.format)
        else:
            return other.__mul__(self)

    def __div__(self, other):
        # If division is illegal (this should definitely not happen)
        if not other or other.c == 0:
            raise RuntimeError("Division by zero")

        # If fraction will be zero
        if self.c == 0:
            return Symbol("", 0, CONST, self.format)

        # In case we get a symbol equal to the one we have the fraction is a
        # constant, else we have a simple fraction
        if isinstance(other, Symbol):
            if self == other:
                return Symbol("", self.c/other.c, CONST, self.format)
            return Fraction(self, other, self.format)

        # We get expanded objects where nested operators have been removed
        # If other is a Sum we can only return a fraction
        elif isinstance(other, Sum):
            return Fraction(self, other, self.format)
        elif isinstance(other, (Symbol, Product)):

            # Create copy of self and save count (possibly new numerator)
            num = self.copy()
            num.c = num.c/other.c

            # Get list of members for potential denominator
            denom_list = other.mbrs()

            # If self is in denominator, remove it and create const numerator
            if num in denom_list:
                denom_list.remove(num)
                num = Symbol("", num.c/other.c, CONST, self.format)

            # Create the denominator and new fraction
            if len(denom_list) > 1:
                return Fraction(num, Product(denom_list, self.format, True), self.format, True)
            elif len(denom_list) == 1:
                return Fraction(num, denom_list[0], self.format, True)
            else:
                return num
        else:
            raise RuntimeError("Product can only be divided by Symbol, Product and Sum")

    def __add__(self, other):
        # If two symbols are equal, just add their counters
        if self == other:
            new = self.copy()
            new.c += other.c
            return new
        else:
            raise RuntimeError("Not implemented")

    def __eq__(self, other):
        "Two symbols are equal if the variable and domain are equal, sign does not have to be equal"
        if isinstance(other, Symbol):
            return self.v == other.v # and self.t == other.t
        else:
            return False

    def __lt__(self, other):
        if isinstance(other, Symbol):
            # First sort by type then by variable name
            if self.t == other.t:
                return self.v < other.v
            elif self.t < other.t:
                return True
            else:
                return False
        # Symbols are always lowest
        return True

    def __gt__(self, other):
        if isinstance(other, Symbol):
            # First sort by type then by variable name
            if self.t == other.t:
                return self.v > other.v
            elif self.t > other.t:
                return True
            else:
                return False
        # Symbols are always lowest
        return False

    def get_unique_vars(self, var_type):
        # Return self if type matches, also return base expression variables
        s = set()
        if self.t == var_type:
            s.add(self)
        if self.base_expr:
            s.update(self.base_expr.get_unique_vars(var_type))
        return s

    def reduce_vartype(self, var_type):
        # Return new self and leave constant in the remainder
        if self.t == var_type:
            new = self.copy()
            new.c = 1
            return (new, Symbol("", self.c, CONST, self.format))
        # Types did not match
        return ([], self.copy())

    def reduce_ops(self):
        # Can't reduce a symbol
        return self.copy()

    def get_vars(self):
        if self.c != 1 and self.c != -1:
            return [self]
        return [None]

    def reduce_var(self, var):
        # Reduce the variable by other variable through division
        return self/var

    def num_var(self, var_name):
        # Get the number of varibles with given name
        if self.v == var_name:
            return 1
        return 0

    def copy(self):
        "Returning a copy"
        # Return a constant if count is zero, else copy of self
        new = Symbol(self.v, self.c, self.t, self.format)
        new.base_expr = self.base_expr
        new.base_op = self.base_op
        return new

    def recon(self):
        "Reconstruct a variable, (returning a copy)"
        if self.c == 0:
            return Symbol("", 0, CONST, self.format)
        return self.copy()

    def mbrs(self):
        """Helper function, just return a copy of self as a list. It makes it
        possible to treat Products and symbols the same way"""
        # Just return list
        return [self.copy()]

    def remove_nested(self):
        "A symbol does not contain nested symbols"
        # Nothing to be done
        return self.recon()

    def expand(self):
        "A symbol can't be expanded"
        # Nothing to be done
        return self.recon()

    def ops(self):
        "Returning the number of floating point operation for symbol"
        # No operations if count is zero
        if self.c == 0:
            return 0

        # Get base ops (like sin(2*x + 1)) --> 2
        ops = self.base_op
        if self.base_expr:
            ops += self.base_expr.ops()

        # Add one operation if we have a non unity count (2*x) not 1*x
        if self.t != CONST and self.c != 1 and self.c != -1:
            ops += 1

        # Add one operation for a minus sign (- x or - 2*x)
        if self.c < 0:
            ops += 1
        return ops

class Product(object):
    def __init__(self, variables, format, copies=False):
        """Initialise a Product object, the class contains:
        vs - a list of symbols
        c  - float, a count of occurrences (constant factor)
        t - Type, one of CONST, GEO, IP, BASIS. It is equal to the lowest
            type of its members"""

        # Save format TODO: Is it possible to define this once outside the
        # classes so that we don't have to 'drag' the format around?
        self.format = format
        self.c = 1
        self.vs = []
#        print "variables: ", variables
        if not variables:
            # Create a const symbols and add to list, no need to proceed
            self.c = 0
            self.t = CONST

        # Check if product is zero
        for v in variables:
            if v == None or v.c == 0:
                # Create a const symbols and add to list, no need to proceed
                self.c = 0
                self.vs = [Symbol("", 0, CONST, self.format)]
                self.t = CONST
                break

        if self.c != 0:
            # Create copies of symbols
            if copies:
                new_vars = variables
            else:
                new_vars = [v.copy() for v in variables]

            # Multiply the count of self by the count of the symbols, then set
            # the count of the symbols equal to 1
            append = self.vs.append
            for v in new_vars:
                self.c *= v.c
                v.c = 1

                # There's no need to have constants in the list we already have
                # the count value
                if isinstance(v, Symbol) and v.t == CONST:
                    continue
                # Add symbol to list and sort
                append(v)

            # The type is equal to the highest variable type
            if self.vs:
                self.t = min([v.t for v in self.vs])
            else:
                self.vs = [Symbol("", 1, CONST, self.format)]
                self.t = CONST
            self.vs.sort()

    def __repr__(self):
        "Representation for debugging"
        # Group and join representation of members
        s = "prod" + self.format["grouping"](" " + ", ".join([v.__repr__() for v in self.vs]) + " ")
        s += self.format["block"](type_to_string[self.t])

        # Only multiply by count if it is different from 1 and -1
        if self.c != 1 and self.c != -1:
            s = self.format["multiply"]([self.format["floating point"](abs(self.c)), s])

        # Add minus sign if appropriate
        if self.c < 0:
            s = self.format["subtract"](["", s])
        return s

    def __str__(self):
        "Simple string representation"
        # If the count is zero, just return a zero float
        if self.c == 0:
            return self.format["floating point"](0.0)

        # Join string representation of members by multiplication
        s = self.format["multiply"]([str(v) for v in self.vs])

        # Only multiply by count if it is needed
        if self.c != 1 and self.c != -1:
            s = self.format["multiply"]([self.format["floating point"](abs(self.c)), s])

        # Add minus sign if needed
        if self.c < 0:
            s = self.format["subtract"](["", s])
        return s

    def __hash__(self):
        return hash(str(self))

    def __mul__(self, other):
        # If product will be zero
        if self.c == 0 or not other or other.c == 0:
            return Symbol("", 0, CONST, self.format)

        # If we get a symbol or another product, create a new product from the
        # members. It is safe because the expressions have been expanded and
        # nested operations removed.
        if isinstance(other, Symbol):

            # Rather than using Product(self.mbrs() + other.mbrs())
            # We create it here and set the count manually to avoid calling recon()
            new = Product(self.vs + [other], self.format)
            new.c = self.c*other.c
            return new
        elif isinstance(other, Product):
            new = Product(self.vs + other.vs, self.format)
            new.c = self.c*other.c
            return new
        else:
            # Let other object handle this
            return other.__mul__(self)

    def __div__(self, other):

        # If division is illegal (this should definitely not happen)
        if not other or other.c == 0:
            raise RuntimeError("Division by zero")

        # If fraction will be zero
        if self.c == 0:
            return Symbol("", 0, CONST, self.format)

        # We get expanded objects where nested operators have been removed
        # If other is a Sum we can only return a fraction
        if isinstance(other, Sum):
            return Fraction(self, other, self.format)

        # If we get a symbol and it is present in the product list, construct
        # new list and remove the symbols
        elif isinstance(other, Symbol):
            if other in self.vs:
                new_list = self.mbrs()
                if other in new_list:
                    new_list.remove(other)
                # If we no longer have a list only a constant is left
                # TODO: Might not be needed because a product of one symbol
                # should have been removed at an earlier stage, but it is OK to
                # leave it
                if not new_list:
                    return Symbol("", self.c/other.c, CONST, self.format)
                # If we still have many symbols, create a new product
                elif len(new_list) > 1:
                    new_list[0].c = self.c/other.c
                    return Product(new_list, self.format, True)
                # If only one symbol is left, just return it
                else:
                    new = new_list[0]
                    new.c = self.c/other.c
                    return new
            # If other was not in the list of symbols, return a fraction
            return Fraction(self, other, self.format)

        elif isinstance(other, Product):

            # If by chance the products are equal return a const
            if self.vs == other.vs:
                return Symbol("", self.c/other.c, CONST, self.format)

            # Get new potential numerator members
            num_list = self.mbrs()

            # List to hold new denominator
            denom_list = []

            # Loop other members, if in list of members remove it else add it
            # to the denominator
            append = denom_list.append
            remove = num_list.remove
            for m in other.vs:
                if m in num_list:
                    remove(m)
                else:
                    append(m.copy())

            # If we still have a list of members, the numerator is a product
            # else it's just a constant
            if not num_list:
                num = Symbol("", self.c/other.c, CONST, self.format)
            elif len(num_list) > 1:
                num = Product(num_list, self.format, True)
                num.c = self.c/other.c
            else:
                num = num_list[0]
                num.c = self.c/other.c

            # If we no longer have a denominator, return the numerator, else
            # return appropriate fraction
            if not denom_list:
                return num
            denom = ""
            if len(denom_list) > 1:
                denom = Product(denom_list, self.format, True)
            else:
                denom = denom_list[0]
            # The numerator already contain the count, so set it to one
            denom.c = 1
            return Fraction(num, denom, self.format, True)
        else:
            raise RuntimeError("Product can only be divided by Symbol, Product and Sum")

    def __add__(self, other):
        # If two products are equal, add their counters
        if self == other:
            new = self.copy()
            new.c += other.c
            return new
        else:
            raise RuntimeError("Not implemented")

    def __eq__(self, other):
        "Two products are equal if their list of variables are equal, sign does not have to be equal"
        if isinstance(other, Product):
            return self.vs == other.vs
        else:
            return False

    def __lt__(self, other):
        # Symbols are always less
        if isinstance(other, Symbol):
            return False
        # Compare list of symbols for two products
        elif isinstance(other, Product):
            return self.vs < other.vs
        # Products are less than sum and fraction
        return True

    def __gt__(self, other):
        # Symbols are always less
        if isinstance(other, Symbol):
            return True
        # Compare list of symbols for two products
        elif isinstance(other, Product):
            return self.vs > other.vs
        # Products are less than sum and fraction
        return False

    def get_unique_vars(self, var_type):
        # Loop all members and get their types
        var = set()
        update = var.update
        for v in self.vs:
            update(v.get_unique_vars(var_type))
        return var

    def num_var(self, var_name):
        # The number of variables with a given name is just the sum of all
        # occurrences of that symbol in the product
        return sum([v.v == var_name for v in self.vs])

    def reduce_ops(self):
        # It's not possible to reduce a product
        return self.recon()

    def reduce_var(self, var):
        # Reduce by another variable by division
        return self/var

    def reduce_vartype(self, var_type):
        # Get a list of all symbols with the given var type and create an
        # appropriate class
        found = [v for v in self.vs if v.t == var_type]

        # To get the remainder, simply divide by created class of found members
        if len(found) > 1:
            found = Product(found, self.format)
        elif found:
            found = found.pop()
        else:
            return (found, self.copy())
        remains = self/found

        return (found, remains)

    def get_vars(self):
        # Get variables without reconstructing them, but be careful when using them
        return self.vs

    def mbrs(self):
        "Get the members, and add total count to first member"
        # Reconstruct members
        members = [v.copy() for v in self.vs]

        # The value of .c for each members was set to 1 when initialising the
        # product, so we need to set one of them to self.c
        members[0].c = self.c
        return members

    def copy(self):
        new = Product([], self.format)
        new.vs = [v.copy() for v in self.vs]
        new.t = self.t
        new.c = self.c
        return new

    def recon(self):
        # If the product is zero return zero Symbol
        if self.c == 0:
            return Symbol("", 0, CONST, self.format)

        # Return new product of members
        if len(self.vs) > 1:
            new_c = self.c
            new_vars = []
            append = new_vars.append
            for v in self.vs:
                new_v = v.recon()
                if new_v == None or new_v.c == 0:
                    return Symbol("", 0, CONST, self.format)
                new_c *= new_v.c
                if isinstance(v, Symbol) and v.t == CONST:
                    continue
                append(new_v)

            new = Product([], self.format)
            new.vs = new_vars
            new.c = new_c
            new.t = self.t
            return new
        # If we have just one member return it
        elif len(self.vs) == 1:
            new = self.vs[0].recon()
            new.c = self.c
            return new
        else:
            # This should never happen
            raise RuntimeError("No members")

    def ops(self):
        "Get the number of operations to compute product"
        # If the product count is zero no operations are needed
        if self.c == 0:
            return 0

        # It takes n-1 operations ('*') for a product of n members
        ops = len(self.vs) - 1

        # Loop members and add their count
        for v in self.vs:
            ops += v.ops()

        # Add an operation for minus
        if self.c < 0:
            ops += 1

        # Add an operation for multiplication of count (2*(x*y*z))
        if self.c != 1 and self.c != -1:
            ops += 1

        return ops

    def remove_nested(self):
        "Remove all nested occurrences of operators in a product"

        # A list for the new products, save count
        new_prods = []
        new_c = self.c

        # Get local functions to speed things up
        append = new_prods.append
        extend = new_prods.extend
#        print "self: ", self
        # Loop all elements of self
        for m in self.vs:
#            print "m: ", m
            # Remove nested from sub expressions
            new_m = m.remove_nested()

            # If we have a product add all it members to the list of products
            # and thereby removing a nested product
            if isinstance(new_m, Product):
                extend(new_m.vs)
                # Don't forget to multiply by count of new instance
                # TODO: This will always be 1 or?
                new_c *= new_m.c

            # If we don't have a product we just add it to the list
            else:
                append(new_m)

        # Something is very wrong if the list is empty
        if not new_prods:
            raise RuntimeError("Where did they go?")

        # If we just have one member of the product, we don't really have a
        # product anymore.
        if len(new_prods) == 1:
            new = new_prods[0]
            new.c = new_c
            return new
        else:
#            new = Product(new_prods, self.format)
            new = Product([], self.format)
            new.c = new_c
            new.vs = new_prods
            new.vs.sort()
            new.t = self.t
            return new

    def expand(self):
        "Expand all members of the product"

        # Remove nested expressions
        new_self = self.remove_nested()

        # If we don't have a product anymore return the expansion of it
        if not isinstance(new_self, Product):
            return new_self.expand()

#        print "\nbeging"
#        print self
#        print new_self

        # Expand all members
        expanded = [m.expand() for m in new_self.vs]

        # If there is anything in the list that will make the product zero
        # Just return a zero const
        if not expanded or None in expanded:
            return Symbol("", 0, CONST, self.format)

        # Add the factor to the first component
        expanded[0].c = new_self.c

#        print "expanded: ", expanded

        # If we only have one member in the list just return it
        # (it is already expanded)
        if len(expanded) == 1:
            return expanded[0]

        # Sort in Symbols and rest
        syms = []
        rest = []
        append_sym = syms.append
        append_rest = rest.append
        for e in expanded:
            if isinstance(e, Symbol):
                append_sym(e)
            else:
                append_rest(e)
#        print "rest: ", rest
#        print "syms: ", syms
#        if syms:
#            append_rest(Product(syms, self.format))
#        return reduce(lambda x, y:x*y, rest)
        if not syms:
            # Multiply all members of the list
            return reduce(lambda x, y:x*y, rest)
        elif len(syms) > 1:
            new = Product(syms, self.format, True)
        else:
            new = syms[0]
        if new.c == 0:
            return Symbol("", 0, CONST, self.format)
        if not rest:
            return new
        else:
            append_rest(new)
            return reduce(lambda x, y:x*y, rest).remove_nested()

class Sum(object):
    def __init__(self, variables, format, copies=False):
        """Initialise a Sum object, the class contains:
        vs - a list of symbols
        c  - float, a count of occurrences (constant factor)
        t - Type, one of CONST, GEO, IP, BASIS. It is equal to the lowest
            type of its members"""

        # Save format TODO: Is it possible to define this once outside the
        # classes so that we don't have to 'drag' the format around?
        self.format = format
        self.pos = []
        self.neg = []
        self.c = 0
        self.t = CONST

        # Create copies of variable, exclude if they are zero valued

        if copies:
            variables = [v for v in variables if v and v.c != 0]
        else:
            variables = [v.copy() for v in variables if v and v.c != 0]

        if variables:
            # Add duplicates
            new_vars = []
            append = new_vars.append
            for c in variables:
                if c in new_vars:
                    i = new_vars.index(c)
                    new_vars[i] += c
                else:
                    append(c)

            # Exclude variables if addition has resulted in zero count (- 2x + 3x - x)
            new_vars = [v for v in new_vars if v.c != 0]
            if new_vars:
                self.c = 1
                self.t = min([v.t for v in new_vars])
            else:
                self.c = 0
                self.t = CONST

            # Determine sign of sum, if negative move outside and remove from vars, then sort
            neg_vars = [v.c < 0 for v in new_vars]
            if neg_vars and all(neg_vars):
                self.c = -1
                for v in new_vars:
                    v.c = abs(v.c)

            # Sort variables in positive and negative, (for representation)
            self.pos = [v for v in new_vars if v.c > 0]
            self.neg = [v for v in new_vars if v.c < 0]
            self.pos.sort()
            self.neg.sort()

    def __repr__(self):
        "Representation for debugging"

        # If the count is zero we're done
        if self.c == 0:
            return self.format["floating point"](0.0)

        # First add all the positive variables using plus, then add all
        # negative using minus
        pos = self.format["add"]([v.__repr__() for v in self.pos])
        neg = pos + "".join([v.__repr__() for v in self.neg])

        # Group the members of the sum and multiply by factor 
        s = "sum" + self.format["grouping"](neg)
        if self.c and self.c != 1 and self.c != -1:
            s = self.format["multiply"]([self.format["floating point"](abs(self.c)), s])

        s += self.format["block"](type_to_string[self.t])
        # Add minus sign
        if self.c < 0:
            s = self.format["subtract"](["", s])
        return s

    def __str__(self):
        "Simple string representation"

        # If the count is zero we're done
        if self.c == 0:
            return self.format["floating point"](0.0)

        # First add all the positive variables using plus, then add all
        # negative using minus
        pos = self.format["add"]([str(v) for v in self.pos])
        neg = pos + "".join([str(v) for v in self.neg])

        # Group only if we have more that one variable
        if len(self.get_vars()) > 1:
            neg = self.format["grouping"](neg)
        # Multiply by count if it is different from 1 and -1
        if self.c and self.c != 1 and self.c != -1:
            neg = self.format["multiply"]([self.format["floating point"](abs(self.c)), neg])
        # Add minus sign
        if self.c < 0:
             neg = self.format["subtract"](["", neg])
        return neg

    def __hash__(self):
        return hash(str(self))

    def __mul__(self, other):

        # If product will be zero
        if self.c == 0 or not other or other.c == 0:
            return Symbol("", 0, CONST, self.format)

        # List of new products
        new_prods = []
        # We expect expanded sub-expressions with no nested operators
        # If we have a symbol or product, multiply each of the members in self
        # with other
        append = new_prods.append
        if isinstance(other, (Symbol, Product)):
            for m in self.get_vars():
                append(m*other)
            if self.c != 1:
                for m in new_prods:
                    m.c *= self.c
        # If we are multiplying two sums, multiply all members of self with all
        # members of other
        elif isinstance(other, Sum):
            for m in self.get_vars():
                for n in other.get_vars():
                    append(m*n)
            # Counts are not 1 multiply all new product
            if self.c != 1 or other.c != 1:
                for m in new_prods:
                    m.c *= self.c * other.c
        # If other is a fraction let it handle the multiplication
        else:
            return other.__mul__(self)

        # Remove zero valued terms
        new_prods = [v for v in new_prods if v.c != 0]

        # Create new sum
        if not new_prods:
            return Symbol("", 0, CONST, self.format)
        elif len(new_prods) > 1:
            return Sum(new_prods, self.format, True)
        return new_prods[0]

    def __div__(self, other):

        # If division is illegal (this should definitely not happen)
        if not other or other.c == 0:
            raise RuntimeError("Division by zero")

        # If fraction will be zero
        if self.c == 0:
            return Symbol("", 0, CONST, self.format)

        # We get expanded objects where nested operators have been removed
        new_sum = []
        append = new_sum.append
        # If by chance we get a sum and it's equal to the sum we have return a
        # const
        if self == other:
            return Symbol("", self.c/other.c, CONST, self.format)

        # If we get a symbol, sum or product, just divide each of the members
        # in self by other and add to the list
        if isinstance(other, (Symbol, Product, Sum)):
            for m in self.get_vars():
                append(m/other)
            if self.c != 1:
                for m in new_sum:
                    m.c *= self.c
        # We should not get a fraction here
        else:
            raise RuntimeError("Can't divide sum by fraction")

        # Remove zero valued terms
        new_sum = [v for v in new_sum if v.c != 0]

        # Create new sum and reconstruct to handle zero count
        if not new_sum:
            return Symbol("", 0, CONST, self.format)
        elif len(new_sum) > 1:
            return Sum(new_sum, self.format, True)
        return new_sum[0]
            
    def __add__(self, other):
        # If two sums are equal, add their counts
        if self == other:
            new = self.copy()
            new.c += other.c
            return new
        else:
            raise RuntimeError("Not implemented")

    def __eq__(self, other):
        "Two sums are equal if their list of variables are equal including sign"
        if isinstance(other, Sum):
            return self.pos == other.pos and self.neg == other.neg
        else:
            return False

    def __lt__(self, other):
        # Symbols and products are always less
        if isinstance(other, (Symbol, Product)):
            return False
        # Compare representation, to get members and sign correct
        elif isinstance(other, Sum):
            return self.get_vars() < other.get_vars()
        # Fractions are always greater
        return True
    def __gt__(self, other):
        # Symbols and products are always less
        if isinstance(other, (Symbol, Product)):
            return True
        # Compare representation, to get members and sign correct
        elif isinstance(other, Sum):
            return self.get_vars() > other.get_vars()
        return False

    def get_vars(self):
        # Return the list of variables without reconstructing them, beware!
        return self.pos + self.neg

    def get_unique_vars(self, var_type):
        # Loop all members and update the set
        var = set()
        update = var.update
        for v in self.get_vars():
            update(v.get_unique_vars(var_type))
        return var

    def reduce_ops(self):
#        print "\nreduce:\n", self
        var = {}
        var_map = {}
        new_self = self.recon()
        for vr in new_self.get_vars():
            variables = vr.get_vars()
            if not variables:
                continue
            for v in variables:
                if not v:
                    continue
                if not v.v in var:
                    var[v.v] = set([vr])
                    var_map[v.v] = v
                    continue
                elif v.v in var:
                    var[v.v].add(vr)
        if not var:
            return new_self
        max_var = max([len(v) for k,v in var.iteritems()])
        if not max_var > 1:
            return new_self

        reduce_vars = None
        reduce_terms = None
        min_occur = 0
        for key,v in var.iteritems():
            k = var_map[key]

            # If this is a variable that we should reduce
            if len(v) == max_var:
                occur = min([vr.num_var(k.v) for vr in v])
                if occur > min_occur:
                    min_occur = occur
                    reduce_vars = [k]
                    reduce_terms = v
                elif occur == min_occur and v == reduce_terms:
                    reduce_vars.append(k)

        if not reduce_terms:
            return new_self
        not_reduce_terms = set()
        add = not_reduce_terms.add
        for k,v in var.iteritems():
            for vr in v:
                if not vr in reduce_terms:
                    add(vr)

        # Start reducing n times v
        new_reduced = []
        append = new_reduced.append
        if len(reduce_vars) > 1 or min_occur > 1:
            reduce_by = Product(reduce_vars*min_occur, self.format)
        else:
            reduce_by = reduce_vars.pop()

#        print "reduce_by: ", reduce_by
        for rt in reduce_terms:
            append(rt.reduce_var(reduce_by))

        # Create the new sum and reduce it further
        reduced_terms = Sum(list(new_reduced), self.format, True).reduce_ops()
        reduced = Product([reduce_by, reduced_terms], self.format, True)
        reduced.c *= self.c

        # Return reduced expression
        if not_reduce_terms:
            not_reduce = Sum(not_reduce_terms, self.format, True).reduce_ops()
            not_reduce.c *= self.c
            new = Sum([reduced, not_reduce], self.format, True)

#            test = new.expand()
#            if not test == self:
#                print "new: ", new.__repr__()
#                print "new: ", new
#                print "self: ", self.pos
#                print "test: ", test.pos
#                error("Not equal")
            return new.remove_nested()
        else:
#            test = reduced.expand().recon()
#            if not test == self:
#                print "1self: ", repr(self)
#                print "1test: ", repr(test)
#                print "1self: ", self
#                print "1test: ", test
#                error("Not equal")
            return reduced.remove_nested()


    def reduce_vartype(self, var_type):

        found = {}
        # Loop members and reduce them by vartype
        for v in self.get_vars():
            f, r = v.reduce_vartype(var_type)
            if not f:
                f = tuple(f)
            if f in found:
                found[f].append(r)
            elif f not in found:
                found[f] = [r]
        # Create the return value
        returns = []
        append = returns.append
        for f, r in found.iteritems():
            if len(r) > 1:
                r = Sum(r, self.format, True)
                r.c *= self.c
            elif r:
                r = r.pop()
                r.c *= self.c
            append((f, r))
        return returns

    def mbrs(self):
        "Get the members, and multiply by global sign"
        # Reconstruct the members
        members = [v.copy() for v in self.get_vars()]

        # Multiply all members by the count of the sum
        for v in members:
            v.c *= self.c

        return members

    def copy(self):
        new = Sum([], self.format)
        new.c = self.c
        new.t = self.t
        new.pos = [v.copy() for v in self.pos]
        new.neg = [v.copy() for v in self.neg]
        return new

    def recon(self):
        # If the count is zero return a zero const
        if self.c == 0:
            return Symbol("", 0, CONST, self.format)

        # If the length of the positive and negative members are more than one
        # return a new sum of the members
        if len(self.get_vars()) > 1:
            new_vars = [v.recon() for v in self.get_vars()]
            for v in new_vars:
                v.c *= self.c
            return Sum(new_vars, self.format, True)

        # If we have one member return it, don't forget to multiply by count
        elif self.get_vars():
            new = self.get_vars()[0].recon()
            new.c *= self.c
            return new
        else:
            raise RuntimeError("No members")

    def ops(self):
        # No operations if count is zero
        if self.c == 0:
            return 0
        ops = 0

        # Add the number of operations from sub-expressions
        for v in self.pos:
            # Add +1 for the +
            ops += v.ops() + 1
        for v in self.neg:
            # Do not add 1 as negative terms have - included in the ops count
            ops += v.ops()

        # Subtract one operation as it only takes n-1 ops to sum n members
        ops -= 1

        # Add one operation in case of non-unit count ( 2*(x+y+z) )
        if self.c != 1 and self.c != -1:
            ops += 1

        # Add one operation for a minus sign (- 2*(x+y+z) )
        if self.c < 0:
            ops += 1
        return ops

    def remove_nested(self):

        new_sums = []
        append = new_sums.append
        extend = new_sums.extend

        # Loop all members
        for m in self.get_vars():

            # Remove nested on sub-expressions
            new_m = m.remove_nested()
            new_m.c *= self.c
            # If we have a sum, just add its members to the list
            # (this removes a nested sum) 
            if isinstance(new_m, Sum):
                for v in new_m.get_vars():
                    # Multiply all members by the count
                    v.c *= new_m.c
                extend(new_m.get_vars())

            # Just add the new expression to the sum
            else:
                append(new_m)

        # We shouldn't have deleted any memebers in the process
        if not new_sums:
            raise RuntimeError("Where did they go?")
        # If only one members is left, return it. Else create a new sum from
        #  the members
        if len(new_sums) == 1:
            return new_sums[0]
        else:
            return Sum(new_sums, self.format, True)

    def expand(self):
        # Remove nested expressions
        new_self = self.remove_nested()

        # If the count is zero return a const
        if new_self.c == 0:
            return Symbol("", 0, CONST, self.format)

        # If we don't have a sum anymore return the expansion of it
        if not isinstance(new_self, Sum):
            return new_self.expand()

        # Expand all members and multiply by count afterwards to avoid
        # reconstructing multiple times
        expanded = [m.expand() for m in new_self.get_vars()]
        for e in expanded:
            e.c *= new_self.c

        # Exclude None and zeros
        expanded = [e for e in expanded if e and e.c != 0]

        # Create new sum and remove nested, then reconstruct to remove zero count
        if not expanded:
            return Symbol("", 0, CONST, self.format)
        elif len(expanded) == 1:
            return expanded[0]
        new_expanded = []
        append = new_expanded.append
        extend = new_expanded.extend
        for e in expanded:
            if isinstance(e, Sum):
                for v in e.get_vars():
                    v.c *= e.c
                extend(e.get_vars())
            else:
                append(e)
        return Sum(new_expanded, self.format, True)

class Fraction(object):
    def __init__(self, numerator, denominator, format, copies=False):
        """Initialise a Fraction object, the class contains:
        num   - the numerator
        denom - the denominator
        c     - a float count of the number of occurrences
        t - Type, one of CONST, GEO, IP, BASIS. It is equal to the lowest
            type of its members"""

        # Save format TODO: Is it possible to define this once outside the
        # classes so that we don't have to 'drag' the format around?
        self.format = format

        # If numerator and denominator are equal, we have a scalar
        if numerator == denominator:
            self.t = CONST
            self.num = Symbol("", 1, CONST, self.format)
            self.denom = Symbol("", 1, CONST, self.format)
            self.c = numerator.c/denominator.c
        else:
            # Create copies of symbols
            if copies:
                self.num = numerator
                self.denom = denominator
            else:
                self.num = numerator.copy()
                self.denom = denominator.copy()
            self.c = self.num.c/self.denom.c
            self.t = min([self.num.t, self.denom.t])
            self.num.c = 1
            self.denom.c = 1

    def __repr__(self):
        "Representation for debugging"

        s = "frac" + self.format["grouping"](" " + self.num.__repr__() + ", " + self.denom.__repr__() + " ")
        if self.t != None:
            s += self.format["block"](type_to_string[self.t])
        if self.c != 1 and self.c != -1:
            s = self.format["multiply"]([self.format["floating point"](abs(self.c)), s])
        if self.c < 0:
            s = self.format["subtract"](["", s])
        return s

    def __str__(self):
        "Simple string representation"

        if self.c == 0:
            return self.format["floating point"](0.0)
        num = ""
        denom = ""
        new = self.recon()
        if not isinstance(new, Fraction):
            return str(new)

        # Handle numerator
        if isinstance(new.num, Fraction):
            num = self.format["grouping"](str(new.num))
        elif isinstance(new.num, Symbol) and new.num.t != CONST:
            num = str(new.num)
        elif isinstance(new.num, (Product, Sum)):
            num = str(new.num)

        # Default
        if not num:
            num = self.format["floating point"](abs(new.c))
        elif new.c != 1 and new.c != -1:
            num = self.format["multiply"]([self.format["floating point"](abs(new.c)), num])

        denom = str(new.denom)
        if isinstance(new.denom, (Product, Fraction)):
            denom = self.format["grouping"](denom)

        s = num + self.format["division"] + denom
        if new.c < 0:
            s = self.format["subtract"](["", s])
        return s

    def __hash__(self):
        return hash(str(self))

    def __mul__(self, other):

        # If product will be zero
        if self.c == 0 or not other or other.c == 0:
            return Symbol("", 0, CONST, self.format)

        # Multiplication of a fraction always involves the numerator, create new
        num = self.get_num()

        # If other by chance is equal to the denominator, we're done
        if other == self.denom:
            num.c *= other.c
            return num

        if isinstance(other, Fraction):
            # Get numerators and denominators and multiply separately
            new_num = self.get_num() * other.get_num()
            new_denom = self.denom * other.denom
            # If they are equal, we just have a const
            if new_num == new_denom:
                return Symbol("", new_num.c/new_denom.c, CONST, self.format)
            return new_num/new_denom
        else:
            # If other is not a fraction, multiply the numerator by it and
            # divide it by the denominator (should reduce it if possible)
            num *= other

            # Create new fraction
            return num/self.denom

    def __add__(self, other):
        # If two fractions are equal add their count
        if self == other:
            new = self.copy()
            new.c = self.c + other.c
            return new
        else:
            raise RuntimeError("Not implemented")

    def __eq__(self, other):
        # Fractions are equal if their denominator and numerator are equal
        if isinstance(other, Fraction):
            return self.denom == other.denom and self.num == other.num
        else:
            return False

    def __lt__(self, other):
        if isinstance(other, Fraction):
            if self.num < other.num:
                return True
            elif self.num == other.num and self.denom < other.denom:
                return True
        return False
    def __gt__(self, other):
        if isinstance(other, Fraction):
            if self.num > other.num:
                return True
            elif self.num == other.num and self.denom > other.denom:
                return True
            else:
                return False
        return True

    def reduce_ops(self):
        # Try to reduce operations and divide to remove common factors
        return self.get_num().reduce_ops()/self.denom.reduce_ops()

    def get_vars(self):
        if isinstance(self.num, Symbol):
            return [self.num]
        elif isinstance(self.num, Product):
            return self.num.vs
        else:
            return None

    def num_var(self, var_name):
        return sum([v.v == var_name for v in self.num.get_vars() if v])

    def reduce_var(self, var):
        return Fraction(self.get_num()/var, self.denom, self.format)

    def reduce_vartype(self, var_type):
        num_found, num_remains = self.get_num().reduce_vartype(var_type)
        denom_found, denom_remains = self.denom.reduce_vartype(var_type)
        found = ""
        remains = ""
        if not denom_found or denom_found.t == CONST:
            found = num_found
        else:
            found = Fraction(num_found, denom_found, self.format, True)
        if not denom_remains or denom_remains.t == CONST:
            remains = num_remains
        else:
            remains = Fraction(num_remains, denom_remains, self.format, True)
        return (found, remains)

    def get_unique_vars(self, var_type):
        var = set()
        var.update(self.num.get_unique_vars(var_type))
        var.update(self.denom.get_unique_vars(var_type))
        return var

    def get_num(self):
        # Convenient recontruction of denominator
        num = self.num.copy()
        num.c = self.c
        return num

    def copy(self):
        new = Fraction(self.num, self.denom, self.format)
        new.c = self.c
        new.t = self.t
        return new

    def recon(self):
        # If count is zero return const zero
        if self.c == 0:
            return Symbol("", 0, CONST, self.format)
        # Reconstruct the numerator and denominator
        num = self.num.recon()
        num.c = self.c
        denom = self.denom.recon()
        # Special handling if the denominator is constant
        # Just return the numerator because the factor has been handled during
        # initialisation
        if isinstance(denom, Symbol) and denom.t == CONST:
            return num
        # Return new fraction
        return Fraction(num, denom, self.format, True)

    def inv(self):
        # Construct inverse, needed by remove_nested (division by fraction)
        return Fraction(self.denom.copy(), self.get_num(), self.format, True)

    def ops(self):
        # If count is zero the number of operations are zero
        if self.c == 0:
            return 0
        # Need to reconstruct because we do this in __str__, if the new
        # instance is not a Fraction just return the ops
        new = self.recon()
        if not isinstance(new, Fraction):
            return new.ops()

        # Get number of ops from the numerator and denominator
        num_op = new.num.ops()
        denom_op = new.denom.ops()

        # Add the two counts and + 1 for the '/' symbol
        ops = num_op + denom_op + 1

        # Add one for the minus sign
        if new.c < 0:
            ops += 1
        # Add one for the count
        if new.c != 1 and new.c != -1:
            ops += 1
            # Subtract one if the numerator is const (we just use the count instead)
            if new.num.t == CONST:
                ops -= 1
        return ops

    def remove_nested(self):

        # Remove nested for numerator and denominator
        num = self.num.remove_nested()
        num.c = self.c
        denom = self.denom.remove_nested()

        # If both the numerator and denominator are fractions, create new
        # numerator and denominator and remove the nested products expressions
        # that might have been created
        if isinstance(num, Fraction) and isinstance(denom, Fraction):
            # Create fraction
            new_num = Product([num.num, denom.denom], self.format, True).remove_nested()
            new_denom = Product([num.denom, denom.num], self.format, True).remove_nested()
            new = Fraction(new_num, new_denom, self.format, True)
            new.c = num.c/denom.c
            return new
        # If the numerator is a fraction, multiply denominators
        elif isinstance(num, Fraction):
            # Create fraction and remove nested in case new where created
            new_denom = Product([num.denom, denom], self.format, True).remove_nested()
            new = Fraction(num.get_num(), new_denom, self.format, True)
            return new

        # If the denominator is a fraction multiply by the inverse and
        # remove the nested products that might have been created
        elif isinstance(denom, Fraction):
            new = Product([num, denom.inv()], self.format, True)
            return new.remove_nested()
        else:
            # If we didn't have a nested fraction, just return a new one
            return Fraction(num, denom, self.format, True)

    def expand(self):
        # Remove all nested operators from expression
        new_self = self.remove_nested()

        # If we no longer have a fraction return expansion of the new object
        if not isinstance(new_self, Fraction):
            return new_self.expand()

        # Create new expanded numerator
        num = new_self.get_num().expand()

        # If denominator is a product or symbol try to reduce before expanding
        # the denominator
        if isinstance(new_self.denom, (Symbol, Product)):
            new_frac = num/new_self.denom

            # Check if we still have a fraction
            if not isinstance(new_frac, Fraction):
                return new_frac.expand()
            # Get new expanded numerator and denominator
            num = new_frac.get_num().expand()
            denom = new_frac.denom.expand()

            return num/denom

        # Just divide by sum
        elif isinstance(new_self.denom, Sum):
            denom = new_self.denom.expand()
            # Use operator __div__ to figure out what to do
            return num/denom
        else:
            raise RuntimeError("Shouldn't have a fraction here")            

