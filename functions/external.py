from __future__ import division
import _general

class CommandLine(_general._Base):
    """A function that takes an executable file and uses that as the function
    to optimize.  So, if you already have a C or C++ executable, you can just
    give that to this function, and you don't have to translate the C code to
    python.  It might run a lot slower than if you translate it, though, 
    depending on the function - Popen is pretty slow.  

    The only requirements for the executable are that it takes as command line
    arguments the function parameters, and spits out to stdout the function
    evaluation at that point.  Nothing else should go to stdout.  
    """

    from mrs.param import Param

    _params = dict(
            exe=Param(default='',
                doc='External function (must be an executable file)'),
            constraintsfile=Param(default='',
                doc='Constraints file, formatted as one "low,high" line for '
                    'each dimension'),
            quiet=Param(type='bool',
                doc="Don't print messages to and from the external program"),
            )

    def setup(self):
        from subprocess import Popen, PIPE
        super(CommandLine, self).setup()
        if not self.exe:
            raise RuntimeError('Must supply an external function!')
        if not self.constraintsfile:
            self._set_constraints(((-50,50),) * self.dims)
        else:
            f = open(self.constraintsfile)
            constraints = []
            for line in f:
                fields = line.split(',')
                constraint = tuple(float(x) for x in fields)
                constraints.append(constraint)
            self._set_constraints(tuple(constraints))

    def __call__(self, vec):
        import sys
        from subprocess import Popen, PIPE
        command = [self.exe]
        for x in vec:
            command.append(repr(x))
        if not self.quiet:
            print >> sys.stderr, 'Sending to program:',' '.join(repr(x) for x in vec)+' '
        func_proc = Popen(tuple(command), stdout=PIPE)
        retcode = func_proc.wait()
        if retcode != 0:
            raise ValueError('External program returned a nonzero exit code')
        retval = func_proc.stdout.readline()
        if not self.quiet:
            print >> sys.stderr, 'Received from program:',retval
        return float(retval)


class Stdin(CommandLine):
    """ Like CommandLine, except the function must take arguments from stdin 
    instead of as command line arguments.  The process is never closed, so 
    execution should be faster.  The executable should be a loop that waits
    on stdin and spits out to stdout.  That behavior can be overridden with 
    restart, which opens the process every time, but still takes parameters
    from stdin.
    """

    _params = dict(
            restart=Param(type='bool',
                doc='Restart the executable for every call instead of keeping'
                    ' it open'),
            )

    def setup(self):
        from subprocess import Popen, PIPE
        super(Stdin, self).setup()
        if not self.restart:
            self.func_proc = Popen((self.exe), stdout=PIPE, stdin=PIPE)

    def __call__(self, vec):
        import sys
        from subprocess import Popen, PIPE
        if self.restart:
            self.func_proc = Popen((self.exe), stdout=PIPE, stdin=PIPE)
        if not self.quiet:
            print >> sys.stderr, 'Sending to program:',' '.join(repr(x) for x in vec)+' '
        self.func_proc.stdin.write(' '.join(repr(x) for x in vec)+'\n')
        retval = self.func_proc.stdout.readline()
        if not self.quiet:
            print >> sys.stderr, 'Received from program:',retval
        return float(retval)
