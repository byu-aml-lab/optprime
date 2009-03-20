#!/usr/bin/env python

from __future__ import division
import sys, optparse, operator

import mrs
from mrs import param
from particle import Particle


# TODO: allow the initial set of particles to be given


class StandardPSO(mrs.MapReduce):
    def __init__(self, opts, args):
        """Mrs Setup (run on both master and slave)"""

        super(StandardPSO, self).__init__(opts, args)

        self.tmpfiles = None
        self.function = param.instantiate(opts, 'func')
        self.motion = param.instantiate(opts, 'motion')
        self.topology = param.instantiate(opts, 'top')

        self.function.setup()
        self.motion.setup(self.function)
        self.topology.setup(self.function)

    ##########################################################################
    # Bypass Implementation

    def bypass(self):
        """Run a "native" version of PSO without MapReduce."""

        self.cli_startup()

        # Perform the simulation in batches
        try:
            for batch in xrange(self.opts.batches):
                # Separate by two blank lines and a header.
                print
                print
                if (self.opts.batches > 1):
                    print "# Batch %d" % batch
                self.bypass_batch(batch)
                print "# DONE" 
        except KeyboardInterrupt, e:
            print "# INTERRUPTED"

    def bypass_batch(self, batch):
        """Performs a single batch of PSO without MapReduce.

        Compare to the run_batch method, which uses MapReduce to do the same
        thing.
        """
        self.setup()
        comp = self.function.comparator

        # Create the Population.
        rand = self.initialization_rand(batch)
        particles = list(self.topology.newparticles(batch, rand))

        # Perform PSO Iterations.  The iteration number represents the total
        # number of function evaluations that have been performed for each
        # particle by the end of the iteration.
        output = param.instantiate(self.opts, 'out')
        output.start()
        for iteration in xrange(1, 1 + self.opts.iters):
            # Update position and value.
            for p in particles:
                self.move_and_evaluate(p)

            # Communication phase.
            for p in particles:
                for i in self.topology.iterneighbors(p):
                    # Send p's information to neighbor i.
                    neighbor = particles[i]
                    neighbor.nbest_cand(p.pbestpos, p.pbestval, comp)
                    if self.opts.transitive_best:
                        neighbor.nbest_cand(p.nbestpos, p.nbestval, comp)

            # Output phase.  (If freq is 5, output after iters 1, 6, 11, etc.)
            if not ((iteration-1) % output.freq):
                kwds = {}
                if 'iteration' in output.args:
                    kwds['iteration'] = iteration
                if 'particles' in output.args:
                    kwds['particles'] = particles
                if 'best' in output.args:
                    best = None
                    bestval = None
                    for p in particles:
                        if (best is None) or comp(p.pbestval, bestval):
                            best = p
                            bestval = p.pbestval
                    kwds['best'] = best
                output(**kwds)
        output.finish()

        self.cleanup()

    ##########################################################################
    # MapReduce Implementation

    def run(self, job):
        """Run Mrs PSO function
        
        This is run on the master.
        """
        self.cli_startup()
        try:
            tty = open('/dev/tty', 'w')
        except IOError:
            tty = None

        # Perform the simulation in batches
        try:
            for batch in xrange(self.opts.batches):
                # Separate by two blank lines and a header.
                print
                print
                if (self.opts.batches > 1):
                    print "# Batch %d" % batch
                self.run_batch(job, batch, tty)
                print "# DONE" 
        except KeyboardInterrupt, e:
            print "# INTERRUPTED"

    def run_batch(self, job, batch, tty):
        """Performs a single batch of PSO using MapReduce.

        Compare to the bypass_batch method, which does the same thing without
        using MapReduce.
        """
        self.setup()
        rand = self.initialization_rand(batch)
        particles = [(str(p.pid), repr(p)) for p in
                self.topology.newparticles(batch, rand)]

        numtasks = self.opts.numtasks
        if not numtasks:
            numtasks = len(particles)
        new_data = job.local_data(particles, parter=mrs.mod_partition,
                splits=numtasks)

        output = param.instantiate(self.opts, 'out')
        output.start()

        # Perform iterations.  Note: we submit the next iteration while the
        # previous is being computed.  Also, the next PSO iteration depends on
        # the same data as the output phase, so they can run concurrently.
        last_best = None
        last_swarm = None
        next_best = None
        for iteration in xrange(1, 1 + self.opts.iters):
            interm_data = job.map_data(new_data, pso_map, splits=numtasks,
                    parter=mrs.mod_partition)
            next_swarm = job.reduce_data(interm_data, pso_reduce,
                    splits=numtasks, parter=mrs.mod_partition)

            if not ((iteration - 1) % output.freq):
                if 'best' in output.args:
                    # Create a new output_data MapReduce phase to find the
                    # best particle in the population.
                    collapsed_data = job.map_data(next_swarm, collapse_map,
                            splits=1)
                    next_best = job.reduce_data(collapsed_data,
                            findbest_reduce, splits=1)

            waitset = set()
            if last_swarm:
                waitset.add(last_swarm)
            if last_best:
                waitset.add(last_best)
            while waitset:
                if tty:
                    ready = job.wait(timeout=1.0, *waitset)
                    if last_swarm in ready:
                        print >>tty, "Finished iteration", last_iteration
                    else:
                        print >>tty, job.status()
                else:
                    ready = job.wait(*waitset)

                ####################################
                # FIX ALL OF THE OUTPUT STUFF HERE:

                if last_swarm in ready:
                    waitset.remove(last_swarm)
                    if 'particles' in output.args:
                        # FIXME
                        pass

                if last_best in ready:
                    # FIXME
                    pass

                # Download output_data and update population accordingly.
                if 'best' in output.args or 'particles' in output.args:
                    output_data.fetchall()
                    particles = []
                    for bucket in output_data:
                        for reduce_id, particle in bucket:
                            particles.append(Particle.unpack(state))

                    if 'particles' in output.args:
                        # FIXME: loop over the particles and find the best.
                        pass
                    else:
                        best = particles[0]

                    # Print out the results.
                    outputter(pop, iters)
                    sys.stdout.flush()

                if not running:
                    job.wait(new_data)
                    break

            # Set up for the next iteration.
            last_iteration = iteration
            last_swarm = next_swarm
            last_best = next_best

        output.finish()

    ##########################################################################
    # Primary MapReduce

    def pso_map(key, value):
        comparator = self.function.comparator
        particle = Particle.unpack(value)
        assert particle.pid == key
        self.move_and_evaluate(particle)

        # Emit a message for each dependent particle:
        message = particle.make_message(self.opts.transitive_best)
        # TODO: create a Random instance for the iterneighbors method.
        for dep_id in self.topology.iterneighbors(particle):
            yield (str(dep_id), repr(message))

        # Emit the particle without changing its id:
        yield (str(key), repr(particle))

    def pso_reduce(key, value_iter):
        comparator = self.function.comparator
        particle = None
        best = None
        bestval = float('inf')

        for value in value_iter:
            record = Particle(pid=int(key), state=value)
            if record.is_message():
                if comparator(record.nbestval, bestval):
                    best = record
                    bestval = record.nbestval
            else:
                particle = record

        if particle:
            particle.nbest_cand(best.nbestpos, bestval, comparator)
            yield repr(particle)
        else:
            raise RuntimeError("Didn't find particle %d in the reduce step" %
                    key)

    ##########################################################################
    # MapReduce to Find the Best Particle

    def collapse_map(key, value):
        yield '0', value

    def findbest_reduce(key, value_iter):
        comparator = self.function.comparator
        best = None
        for value in value_iter:
            p = Particle.unpack(value)
            if (best is None) or (comparator(p.pbestval, best.pbestval)):
                best = p
        yield repr(best)

    ##########################################################################
    # Helper Functions (shared by bypass and mrs implementations)

    def move_and_evaluate(self, p):
        """Moves, evaluates, and updates the given particle."""
        self.set_particle_rand(p)
        if p.iters > 0:
            newpos, newvel = self.motion(p)
        else:
            newpos, newvel = p.pos, p.vel
        # TODO(?): value = self.function(newpos, p.rand)
        value = self.function(newpos)
        p.update(newpos, newvel, value, self.function.comparator)

    def set_particle_rand(self, p):
        """Makes a Random for the given particle and saves it to `p.rand`.

        Note that the Random depends on the particle id, iteration, and batch.
        """
        from mrs.impl import SEED_BITS
        base = 2 ** SEED_BITS
        offset = 1 + base * (p.pid + base * (p.iters + base * p.batches))
        p.rand = self.random(offset)

    def initialization_rand(self, batch):
        """Returns a new Random for the given batch number.

        This ensures that each batch will have a unique initial swarm state.
        """
        from mrs.impl import SEED_BITS
        base = 2 ** SEED_BITS
        offset = 2 + base * batch
        return self.random(offset)

    def cli_startup(self):
        """Checks whether the repository is dirty and reports options."""
        import cli
        import sys

        # Check whether the repository is dirty.
        mrs_status = cli.GitStatus(mrs)
        amlpso_status = cli.GitStatus(sys.modules[__name__])
        if not self.opts.hey_im_testing:
            if amlpso_status.dirty:
                print >>sys.stderr, (('Repository amlpso (%s) is dirty!'
                        '  Use --hey-im-testing if necessary.') %
                        amlpso_status.directory)
                sys.exit(-1)
            if mrs_status.dirty:
                print >>sys.stderr, (('Repository mrs (%s) is dirty!'
                        '  Use --hey-im-testing if necessary.') %
                        mrs_status.directory)
                sys.exit(-1)

        # Report command-line options.
        if not self.opts.quiet:
            import email
            date = email.Utils.formatdate(localtime=True)
            print '#', sys.argv[0]
            print '# Date:', date
            print '# Git Status:'
            print '#   amlpso:', amlpso_status
            print '#   mrs:', mrs_status
            print "# Options:"
            for key, value in sorted(vars(self.opts).iteritems()):
                print '#   %s = %s' % (key, value)
            print ""
            sys.stdout.flush()

    def setup(self):
        try:
            self.tmpfiles = self.function.tmpfiles()
        except AttributeError:
            self.tmpfiles = []

    def cleanup(self):
        for f in self.tmpfiles:
            os.unlink(f)


##############################################################################
# Busywork

def update_parser(parser):
    """Adds PSO options to an OptionParser instance."""
    # Set the default Mrs implementation to Bypass (instead of MapReduce).
    parser.usage = parser.usage.replace('Serial', 'Bypass')
    parser.set_default('mrs', 'Bypass')

    parser.add_option('-q', '--quiet',
            dest='quiet', action='store_true',
            help='Refrain from printing version and option information',
            default=False,
            )
    parser.add_option('-v','--verbose',
            dest='verbose', action='store_true',
            help="Print out verbose error messages",
            default=False,
            )
    parser.add_option('-b','--batches',
            dest='batches', type='int',
            help='Number of complete experiments to run',
            default=1,
            )
    parser.add_option('-i','--iters',
            dest='iters', type='int',
            help='Number of iterations per batch',
            default=100,
            )
    parser.add_option('-f','--func', metavar='FUNCTION',
            dest='func', action='extend', search=['functions'],
            help='Function to optimize',
            default='sphere.Sphere',
            )
    parser.add_option('-m','--motion',
            dest='motion', action='extend', search=['motion.basic', 'motion'],
            help='Particle motion type',
            default='Constricted',
            )
    parser.add_option('-t','--top', metavar='TOPOLOGY',
            dest='top', action='extend', search=['topology'],
            help='Particle topology/sociometry',
            default='Complete',
            )
    parser.add_option('-o', '--out', metavar='OUTPUTTER',
            dest='out', action='extend', search=['output'],
            help='Style of output',
            default='Basic',
            )
    parser.add_option('-N', '--num-tasks',
            dest='numtasks', type='int',
            help='Number of tasks (if 0, create 1 task per particle)',
            default=0,
            )
    parser.add_option('--transitive-best',
            dest='transitive_best', action='store_true',
            help='Whether to send nbest to others instead of pbest',
            default=False
            )
    parser.add_option('--hey-im-testing',
            dest='hey_im_testing', action='store_true',
            help='Ignore errors from uncommitted changes (for testing only!)',
            default=False,
            )

    return parser


if __name__ == '__main__':
    mrs.main(StandardPSO, update_parser)

# vim: et sw=4 sts=4
