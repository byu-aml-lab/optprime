from __future__ import division
import operator
from math import sqrt

from mrs.param import ParamObj, Param
from ..cube import Cube

try:
    from numpy import empty
except ImportError:
    from numpypy import empty

try:
    range = xrange
except NameError:
    pass


class _Base(ParamObj):
    def setup(self, function, *args, **kargs):
        if function.maximize:
            self.comparator = operator.gt
        else:
            self.comparator = operator.lt
        constraints = function.constraints
        self.dims = len(constraints)
        self.cube = Cube(constraints)
        sizes = [abs(cr-cl) for cl,cr in constraints]
        vconstraints = [(-s,s) for s in sizes]
        self.vcube = Cube(vconstraints)

    def __call__(self, particle, rand):
        raise NotImplementedError


class Constricted(_Base):
    _params = dict(
        phi1=Param(default=2.05, type='float', doc='Value of phi_1 constant'),
        phi2=Param(default=2.05, type='float', doc='Value of phi_2 constant'),
        kappa=Param(default=1, type='float',
            doc="Clerc's Kappa value, always in (0,1)"),
        restrictvel=Param(type='bool', doc='Restrict velocities'),
        )

    def __init__(self):
        super(Constricted, self).__init__()

        phi = self.phi1 + self.phi2
        kappa = self.kappa
        if phi > 4:
            self.const = 2*kappa/abs(2 - phi - sqrt(phi**2 - 4*phi))
        else:
            self.const = kappa

    def __call__(self, particle, rand):
        """Get the next position and velocity from this particle."""

        # TODO: once numpypy supports the numpy.random module, use it instead.
        r1 = rand_uniform(0, self.phi1, self.dims, rand)
        r2 = rand_uniform(0, self.phi2, self.dims, rand)

        grel = particle.nbestpos - particle.pos
        prel = particle.pbestpos - particle.pos
        newvel = self.const * (particle.vel + grel*r1 + prel*r2)

        if self.restrictvel:
            self.vcube.constrain_vec(newvel)

        return particle.pos + newvel, newvel


class BasicAdaptive(_Base):
    _params = dict(
        k=Param(default=-0.5, type='float',
            doc='Friction coefficient -- usually should be negative'),
        dt=Param(default=1.0, type='float',
            doc='Initial time step for each particle'),
        step_inc=Param(default=1.5, type='float',
            doc='Amount to increment the timestep (multiply)' ),
        step_dec=Param(default=0.5, type='float',
            doc='Amount to decrement the timestep (multiply)' ),
        max_err_inc=Param(default=0.1, type='float',
            doc='Maximum allowed error' ),
        c1=Param(default=2.0, type='float',
            doc='first random constant multiplier' ),
        c2=Param(default=2.0, type='float',
            doc='second random constant multiplier' ),
        )

    def setup(self, *args, **kargs):
        super(BasicAdaptive, self).setup(*args, **kargs)

    def __call__(self, particle, rand):
        """Adaptation of the APSO (Tsou and MacNish) -- this actually always
        keeps the position whether we liked it or not (easier with this code
        base) and performs the step calculations right before diving into the
        next calculation.
        """

        if not hasattr(particle, 'prev_val'):
            particle.prev_val = particle.val

        if not hasattr(particle, 'dt'):
            particle.dt = self.dt

        # Now decide whether to decrement the time step or not.

        dims, k, c1, c2 = self.dims, self.k, self.c1, self.c2

        r1 = rand_uniform(0, c1, dims, rand)
        r2 = rand_uniform(0, c2, dims, rand)

        pos, vel, dt = particle.pos, particle.vel, particle.dt

        # This needs to be changed to allow for maximization and negative
        # values If the current value is better than the last, then we increase
        # the time step, otherwise if we're within an allowable range, we
        # decrease it.
        if self.comparator(particle.val, particle.prev_val):
            particle.dt *= self.step_inc
        elif particle.val / particle.prev_val >= self.max_err_inc:
            particle.dt *= self.step_dec
            vel *= self.step_dec

        grel = particle.nbestpos - pos
        prel = particle.pbestpos - pos

        acc = r1 * grel + r2 * prel + k * vel

        newvel = vel + acc * dt
        newpos = pos + vel * dt + (acc * dt**2)/2

        # Store the value before the state change for future use
        particle.prev_val = particle.val

        return newpos, newvel


class BasicGauss(_Base):
    def __call__(self, particle, rand):
        """Get the next velocity from this particle given a particle that it
        should be moving toward"""

        phi = 2/0.97225 # per Clerc's 2003 TRIBES paper
        chi = 1/(phi - 1 + sqrt(phi**2 - 2*phi))

        grel = particle.nbestpos - particle.pos
        prel = particle.pbestpos - particle.pos

        # Generate a Gaussian around the velocity vectors according to Clerc's
        # paper.
        gvel = array([rand.gauss(x,abs(x)/2) for x in grel])
        pvel = array([rand.gauss(x,abs(x)/2) for x in prel])

        newvel = chi * (particle.vel + gvel + pvel)

        return None, newvel

# TODO: once numpypy supports the numpy.random module, use it instead.
def rand_uniform(a, b, n, rand):
    """Draw an array of n random variables distributed as Uniform(a, b)."""
    v = empty(n)
    for i in range(n):
        v[i] = rand.uniform(a, b)
    return v
