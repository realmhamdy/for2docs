'''
Created on Aug 8, 2014
@author: Mohammed Hamdy
'''

import re
from itertools import dropwhile

class Parser(object):
  
  COMMENT_LINE_REGEX = re.compile(r"[!\s*]+(?P<comment>.*$)")
  SPLITTER_REGEX = re.compile(r"\s*,\s*")
  
  @classmethod
  def parse(cls, arg):
    pass
  
  @classmethod
  def parseComments(cls, string):
    # parse comments from the start of string
    # return the comments and the rest of the string
    lines = string.split("\n")
    comment_regex = cls.COMMENT_LINE_REGEX
    comment_lines = []
    for i, line in enumerate(lines):
      stripped = line.strip() # check for empty lines. They belong to the comments
      if not stripped:
        comment_lines.append("\n") # preserve paragraphs ...
      else:
        match = comment_regex.match(stripped)
        if not match: # start of text
          break
        result_dict = match.groupdict()
        comment_lines.append(result_dict["comment"])
    comment = "\n".join(comment_lines)
    rest = "\n".join(lines[i:])
    return comment, rest
  
  @classmethod
  def isCommentLine(cls, line):
    return line.strip().startswith('!')
  
  @classmethod
  def removeStrayComments(cls, string):
    is_comment_line = cls.isCommentLine
    for line in string.split("\n"):
      if is_comment_line(line):
        string = string.replace(line, '')
    return string
  
  @classmethod
  def removeExtras(cls, string):
    # remove stray comments and IMPLICIT NONE
    string = cls.removeStrayComments(string)
    lines = string.split("\n")
    lines = filter(lambda line : "implicit none" not in line.lower(), lines)
    return "\n".join(lines)
        
  @classmethod
  def parse_conditionals(cls, text, defines):
    def eval_conditional(matchobj):
        statement = matchobj.groups()[1].split('#else')
        statement.append('') # in case there was no else statement
        if matchobj.groups()[0] in defines: return statement[0]
        else: return statement[1]

    pattern = r'#ifdef\s*(\S*)\s*((?:.(?!#if|#endif))*.)#endif'
    regex = re.compile(pattern, re.DOTALL)
    while True:
        if not regex.search(text): break
        text = regex.sub(eval_conditional, text)
    return text
        
class FileParser(Parser):
  
  class File(object):
    def __init__(self, comment, modules, dependencies, subroutines):
      self.comment = comment
      self.modules = modules
      self.dependencies = dependencies
      self.subroutines = subroutines
  
  @classmethod
  def parse(cls, fileString, defines):
    fileString = cls.parse_conditionals(fileString, defines)
    comments, rest = cls.parseComments(fileString)
    modules = ModuleParser.parse(rest)
    deps = DependencyParser.parse(rest)
    subrotutines = IndependentSubroutineParser.parse(rest)
    result = cls.File(comments, modules, deps, subrotutines)
    return result
  
class ProgramParser(FileParser):
  
  PROGRAM_CHECKER_REGEX = re.compile(r"^\s*program\s*(?P<program_name>[_\w\d]+)", re.MULTILINE | re.IGNORECASE)
  
  class Program(FileParser.File):
    def __init__(self, parentObject):
      FileParser.File.__init__(self, parentObject.comment, parentObject.modules,
                                         parentObject.dependencies, parentObject.subroutines)
  
  @classmethod
  def parse(cls, programString, defines):
    # parse a program file and return a Program object
    comment_modules_deps_subs = FileParser.parse(programString, defines)
    return cls.Program(comment_modules_deps_subs)
  
  @classmethod
  def isProgram(cls, fileString):
    """Should be called by main to check whether to parse a program or a normal file"""
    checker_regex = cls.PROGRAM_CHECKER_REGEX
    match = checker_regex.search(fileString)
    if not match:
      return False
    return True
  
  
class ModuleParser(Parser):
  
  MODULE_EXTRACTOR_REGEX = re.compile(r"^\s*(?!!)module\s*(?P<module_name>\w+)\s*$(?P<module_content>.*)end\s*module\s*(?P=module_name)?",
                                       re.MULTILINE | re.DOTALL | re.IGNORECASE)
  
  class Module(object):
    def __init__(self, name, comment, classes, dependencies, subroutines, interfaces):
      self.name = name
      self.comment = comment
      self.classes = classes
      self.dependencies = dependencies
      self.subroutines = subroutines
      self.interfaces = interfaces
      
  @classmethod
  def parse(cls, fileString):
    # returns a list of Module object parsed from the file
    module_regex = cls.MODULE_EXTRACTOR_REGEX
    module_matches = module_regex.finditer(fileString)
    # I want to know how to parse the module comment
    modules = []
    for match in module_matches:
      result_dict = match.groupdict()
      module_name = result_dict["module_name"].strip()
      module_content = result_dict["module_content"]
      # assuming the comment is after the first line of module
      module_comment, rest = cls.parseComments(module_content)
      classes = ClassParser.parse(rest)
      dependecies = DependencyParser.parse(rest)
      subroutines = ModuleSubroutineParser.parse(rest)
      interfaces = InterfaceParser.parse(rest)
      modules.append(cls.Module(module_name, module_comment, classes, dependecies, subroutines, interfaces))
    return modules
  
class DependencyParser(Parser):
  
  DEPENDENCY_REGEX = re.compile(r"(?!!)\s*use(,\s+(?:intrinsic|non_intrinsic))?\s*(?:::)?\s+(?P<dependency>\w+)",
                                re.IGNORECASE)
  
  @classmethod
  def parse(cls, string):
    """
    Parse string and return a list of used module names as strings
    string:
      Expected to be a module string or file string
    """
    lines = string.split("\n")
    dependencies = []
    dependency_regex = cls.DEPENDENCY_REGEX
    for line in lines:
      line = line.strip()
      match = dependency_regex.match(line)
      if match:
        result_dict = match.groupdict()
        dependency = result_dict["dependency"]
        if dependency not in dependencies:
          dependencies.append(result_dict["dependency"])
    return dependencies
  
  @classmethod
  def isDependencyLine(cls, line):
    line = line.strip()
    match = cls.DEPENDENCY_REGEX.match(line)
    return bool(match)
  
  @classmethod
  def removeDependencies(cls, string):
    # usually called by SubroutineParser to remove dependencies being parsed as arguments, variables
    deprex = cls.DEPENDENCY_REGEX
    for line in string.split("\n"):
      string = string.replace(line, deprex.sub('', line))
    return string
  
class ClassParser(Parser):
  
  CLASS_REGEX = re.compile(r"^\s*(?!!)\btype\b\s*(,\s*(?P<access_mod>abstract|private|public))?" +\
                           r"(\s*,\s*extends\s*\(\s*(?P<parent>\w+)\s*\))?\s*(::)?\s*(?P<class_name>\w+)\b" +\
                           r"(?P<class_body>.*?)end\s*type\s*(?P=class_name)?", 
                           re.MULTILINE | re.DOTALL | re.IGNORECASE)
  
  class Class(object):
    def __init__(self, className, accessMod, parentName, comment, variables, subroutines):
      self.name = className
      self.access_modifier = accessMod
      self.parent = parentName
      self.comment = comment
      self.variables = variables
      self.subroutines = subroutines
  
  @classmethod
  def parse(cls, moduleString):
    # returns a list of Class objects found in the [module]
    class_regex = cls.CLASS_REGEX
    class_matches = class_regex.finditer(moduleString)
    classes = []
    for match in class_matches:
      result_dict = match.groupdict()
      class_name = result_dict["class_name"]
      access_modifier = result_dict["access_mod"]
      class_content = result_dict["class_body"]
      parent_class = result_dict["parent"]
      # again, assuming the comment is inside the class
      class_comment, rest = cls.parseComments(class_content)
      variables = ClassArgumentParser.parse(rest)
      subroutines = ClassSubroutineParser.parse(moduleString, class_content)
      classes.append(cls.Class(class_name, access_modifier, parent_class, class_comment, variables, subroutines))
    return classes

class ArgumentParser(Parser):
  """
  Parses class variables and subroutine arguments 
  """
  """
  In a declaration like:
    real(mcp), allocatable, dimension(:) :: bao_err
  I consider "allocatable, dimension(:)" as [extras] when parsing.
  """
  # should match with here: http://en.wikibooks.org/wiki/Fortran/Fortran_variables
  # this matches much more than variables, like language constructs, but no easy way out
  VARIABLE_REGEX = re.compile(r"(?P<type_name_args>\w+\s*(\(\s*[\w\.=:\*]+\s*\)|precision)?)\s*" +\
                              r"(,\s*(?P<extra>(\w+(\(.*?\))?)))*" +\
                              r"\s*(::)?\s*" +\
                              r"(?P<var_names>([\w)(:]+(\s*,\s*)?)+)" +\
                              r"\s*(!+(?P<variable_comment>.*))?")
  # subroutine arguments can be defined in body with their name appended with (:) or like
  ARGUMENT_NAME_TEMPLATE_REGEX = "{}(\(:\))?" # substitute the argument name here
                             
  class Argument(object):
    def __init__(self, name, type, extras, comment):
      # extras will be a comma separated string
      self.name = name
      self.type = type
      self.extras = extras
      self.comment = comment
      
  @classmethod
  def parse(cls, string):
    # string is expected to be a class string or subroutine string
    variable_matcher = cls.VARIABLE_REGEX
    splitter_matcher = cls.SPLITTER_REGEX
    arguments = [] # could also be variables
    # perform a line search. should be faster
    for line in string.split("\n"):
      line = line.strip()
      match = variable_matcher.match(line)
      if match:
        result_dict = match.groupdict()
        arg_comment = result_dict["variable_comment"]
        arg_type = result_dict["type_name_args"]
        arg_extras = result_dict["extra"]
        if arg_extras:
          arg_extras = ','.join(splitter_matcher.split(arg_extras))
        arg_names = result_dict["var_names"].strip()
        arg_names = splitter_matcher.split(arg_names)
        for arg_name in arg_names:
          arguments.append(cls.Argument(arg_name, arg_type, arg_extras, arg_comment)) 
    return arguments

class ClassArgumentParser(ArgumentParser):
  """
  Strips the variable portion of the class definition before delegating
  to ArgumentParser
  """
  
  VARIABLE_PORTION_EXTRACTOR = re.compile("(?P<variable_area>.*)contains", re.DOTALL)
  
  @classmethod
  def parse(cls, classString):
    portion_extractor = cls.VARIABLE_PORTION_EXTRACTOR
    match = portion_extractor.search(classString)
    if match:
      variable_area = match.group("variable_area")
      return ArgumentParser.parse(variable_area)
    else: # maybe the class doesn't have subroutine section. the definition should be short and safe for ArgumentParser
      return ArgumentParser.parse(classString)

class SubroutineParser(Parser):
  """Parses subroutines"""
  
  SUBROUTINE_REGEX =  re.compile(r"^\s*(?!!)(?P<return_type>\w+(\(.*\))?)?\s*" +\
                      r"(recursive|logical|integer|real\(.*\)|complex\(.*\)|type\(.*\))?" +\
                      r"\s*(?P<category>subroutine|function)\s*(?P<subname>\w+)\s*" +\
                      r"\((?P<argnames>(\w(\s*,\s*)?)+)\)\s*(result\((?P<result_name>(\w+))\))?" +\
                      r"(?P<subbody>.*?end\s*(?P=category)\s*(?P=subname)?)",
                      re.IGNORECASE | re.DOTALL | re.MULTILINE)
                     
  SUBROUTINE_ALIAS_REGEX = re.compile(r"procedure\s*::\s*(?P<subname>\w+)\s*=>\s*(?P<alias>\w+)\s*",
                                      re.IGNORECASE)
  
  class Subroutine(object):
    def __init__(self, category, name, alias, arguments, comment, resultName, returnType):
      # category means either a 'function' or 'subroutine'
      self.category = category
      self.name = name 
      self.alias = alias
      self.arguments = arguments
      self.comment = comment
      self.result_name = resultName
      self.typeString = returnType
      
    def __eq__(self, other):
      # enough if they have same names
      return self.name == other.name
    
    def __hash__(self):
      name_sum = 0
      for (i, letter) in enumerate(self.name):
        name_sum += i * ord(letter)
      return name_sum
      
  @classmethod
  def parse(cls, string):
    """
    string:
      Could be a module string or program string
    """
    # separate subroutines from each other, so the VariableParser can work correctly
    subroutine_matcher = cls.SUBROUTINE_REGEX
    alias_matcher = cls.SUBROUTINE_ALIAS_REGEX
    argument_template = ArgumentParser.ARGUMENT_NAME_TEMPLATE_REGEX
    alias_matches = list(alias_matcher.finditer(string))
    found_aliases = [match.group("alias") for match in alias_matches]
    splitter = cls.SPLITTER_REGEX
    subroutine_matches = subroutine_matcher.finditer(string)
    subroutines = []
    for sub_match in subroutine_matches:
      actual_args = []
      result_dict = sub_match.groupdict()
      subname = result_dict["subname"]
      subbody = result_dict["subbody"]
      subcomment, rest = cls.parseComments(subbody)
      rest = cls.removeExtras(rest)
      rest = DependencyParser.removeDependencies(rest)
      parsed_arguments = ArgumentParser.parse(rest) # this could also parse other things like subroutine variables
      subalias = ''
      if subname in found_aliases: # procedure/subroutine/function has an alias, assign it 
        for match in alias_matches:
          if match.group("alias") == subname:
            subname, subalias = match.group("subname"), match.group("alias")
            break
      category = result_dict["category"].lower()
      argnames = result_dict["argnames"]
      argnames = splitter.split(argnames)
      compiled_argument_templates = [re.compile(argument_template.format(argname)) for argname in argnames]
      result_name = result_dict["result_name"]
      return_type = result_dict["return_type"] 
      if category == "function" and return_type is None: # didn't find type in header
        for argument in parsed_arguments:
          argument_match_template = re.compile(argument_template.format(result_name))
          if argument_match_template.match(argument.name) or argument.name == subname or argument.name == subalias: # because the subname can be a variable
            if argument.extras:
              return_type = ' '.join([argument.type, argument.extras])
            else:
              return_type = argument.type
            break
        else: # can't help
          pass
      for argument in parsed_arguments:
        for cat in compiled_argument_templates:
          if cat.match(argument.name): # this filters subroutine variables in
            actual_args.append(argument)
            compiled_argument_templates.remove(cat) # only the first match of argument name counts
      subroutines.append(cls.Subroutine(category, subname, subalias, actual_args, subcomment, result_name, return_type))
    return subroutines
  
class IndependentSubroutineParser(SubroutineParser):
  """
  Eliminates modules and classes before passing the job to SubroutineParser
  """
  
  @classmethod
  def parse(cls, string):
    module_matcher = ModuleParser.MODULE_EXTRACTOR_REGEX
    class_matcher = ClassParser.CLASS_REGEX
    no_mod_string = module_matcher.sub('', string)
    no_class_string = class_matcher.sub('', no_mod_string)
    return SubroutineParser.parse(no_class_string)
  
class ModuleSubroutineParser(SubroutineParser):
  """
  Finds module subroutines and class subroutines. Then returns the difference
  """
  
  @classmethod
  def parse(cls, moduleString):
    class_matcher = ClassParser.CLASS_REGEX
    all_subroutines = set(SubroutineParser.parse(moduleString))
    class_bodies = [match.group("class_body") for match in class_matcher.finditer(moduleString)]
    classes_subroutines = set()
    for class_body in class_bodies:
      class_subroutines = ClassSubroutineParser.parse(moduleString, class_body)
      classes_subroutines.update(class_subroutines)
    module_only_subroutines = all_subroutines.difference(classes_subroutines)
    return module_only_subroutines
  
class ClassSubroutineParser(SubroutineParser):
  """
  Passes the whole string to SubroutineParser then picks up only the subroutines that belong
  to the class string passed
  """
  
  PROC_REGEX = re.compile(r"procedure.*::\s*(?P<procedure_name>\w+)\s*(=>\s*(?P<procedure_alias>\w+))?", re.IGNORECASE)
  
  @classmethod
  def parse(cls, wholeString, classBody):
    all_subroutines = SubroutineParser.parse(wholeString)
    class_inner_subroutines = SubroutineParser.parse(classBody)
    procrex = cls.PROC_REGEX
    # find procedures inside class body, then pick them from the whole string subroutines
    class_procedures = procrex.finditer(classBody)
    all_class_subroutines = class_inner_subroutines
    for class_procedure in class_procedures:
      match_dict = class_procedure.groupdict()
      procedure_name = match_dict["procedure_name"]
      procedure_alias = match_dict["procedure_alias"]
      for file_subroutine in all_subroutines:
        if procedure_alias: # if there's an alias, never match on name, to avoid duplicate subroutines
          if file_subroutine.alias == procedure_alias:
            all_class_subroutines.append(file_subroutine)
            break
        elif not file_subroutine.alias and file_subroutine.name == procedure_name:
            all_class_subroutines.append(file_subroutine)
            break
    return all_class_subroutines
  
class InterfaceParser(Parser):
  
  INTEFACE_REGEX = re.compile(r"\s*(?!!)interface\s*(?P<interface_name>\w+)\s*module\s*procedure\s*" +\
                              r"(?P<procedure_names>(\w+(\s*,\s*)?)+)\s*end\s*interface\s*(?P=interface_name)?",
                              re.IGNORECASE)
  
  class Interface(object):
    def __init__(self, name, procedureList):
      self.name = name
      self.procedure_list = procedureList
  
  @classmethod
  def parse(cls, string):
    # parse the procedure list as strings
    irex = cls.INTEFACE_REGEX
    comma_splitter_rex = cls.SPLITTER_REGEX
    interface_matches = irex.finditer(string)
    interfaces = []
    for match in interface_matches:
      result_dict = match.groupdict()
      interface_name = result_dict["interface_name"]
      procedures = result_dict["procedure_names"]
      procedure_names = []
      if procedures:
        procedure_names = comma_splitter_rex.split(procedures)
      interfaces.append(cls.Interface(interface_name, procedure_names))
    return interfaces