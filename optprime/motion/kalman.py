from __future__ import division

import sys

from mrs.param import Param
from numpy import array, dot, transpose, identity, zeros
from numpy.random.mtrand import RandomState
from numpy.linalg import inv

try:
    range = xrange
except NameError:
    pass

from . import basic
from ..particle import Particle


class Kalman(basic._Base):
    _params = dict(
            cfac=Param(default=0.01, type='float', doc='Covariance factor' ),
            predict=Param(default=1, type='int', 
                doc='Predict instead of just filtering' ),
            randinit=Param(default=0, type='int', 
                doc='Initialize to random priors' ),
            velmultiplier=Param(default=1.0, type='float', 
                doc='Multiplier for velocities' ),
            norandscale=Param(default=0, type='int', 
                doc='Remove random scaling from the process' ),
            usepbest=Param(default=0, type='int', 
                doc='Add the use of pbest to the mix' ),
            pgrelationship=Param(default=0.7, type='float', 
                doc='Strength of the relationship between nbest and pbest' ),
        )

    def setup(self, function, *args, **kargs):
        super(Kalman, self).setup(function, *args, **kargs)
        self.constraints = function.constraints

        self.filters = {}

    def getfilter(self, particle, rand):
        if particle.id in self.filters:
            return self.filters[particle.id]

        cfac = self.cfac
        dims = self.dims
        lengths = [abs(r-l) for l,r in self.constraints]

        if self.randinit:
            from cubes.cube import Cube
            c = Cube(self.constraints)
            prior = c.random_vec(rand) + c.random_vec(rand)
        else:
            prior = list(particle.pos) + list(particle.vel)

        # NOTE: The code below should NOT BE CHANGED, no matter how dumb it
        # seems.  You will note that the size of the identity matrices which
        # are serving as starting points for covariances are 2d by 2d.  The
        # loops, however, only iterate over d elements!  This means that the
        # position has a covariance based on the size of the space and the
        # velocity has a covariance based on a static number.  THIS WORKS.  DO
        # NOT CHANGE IT.

        pcov = identity(dims*2)
        for i in range(dims):
            pcov[i][i] = cfac * lengths[i]
            pcov[i+dims][i+dims] = pcov[i][i]

        trans = identity(dims*2)
        for i in range(dims):
            trans[i][i+dims] = self.velmultiplier # Add velocity to position

        tcov = identity(dims*2)
        for i in range(dims):
            tcov[i][i] = cfac * lengths[i]
            tcov[i+dims][i+dims] = tcov[i][i]

        if not self.usepbest:
            cchar = identity(dims)
            ccov = identity(dims)
            for i in range(dims):
                ccov[i][i] = cfac * lengths[i]
        else:
            cchar = identity(dims*2)
            for i in range(dims):
                cchar[i+dims][i] = 1
                cchar[i+dims][i+dims] = 0
            ccov = identity(dims*2)
            for i in range(dims):
                v = cfac * lengths[i]
                ccov[i][i] = v
                ccov[i+dims][i] = self.pgrelationship
                ccov[i][i+dims] = self.pgrelationship
                ccov[i+dims][i+dims] = v

        kalman = KalmanFilter( prior, pcov, trans, tcov, cchar, ccov )

        # TODO: Add this back in if we need to
        #kalman.add( particle.pos )

        self.filters[particle.id] = kalman
        return self.filters[particle.id]

    def __call__(self, particle, rand):
        """Get the next velocity from this particle given a particle that it
        should be moving toward"""
        # I'm not sure what "given a particle that it should be moving toward"
        # means.  We only take one argument, and that's "this particle"

        # In a Bypass mrs implementation (and possibly also with Serial),
        # Kalman motion should work just fine.  However, in parallel, the state
        # required for each particle's motion is not persistent.  We would need
        # to add a "motion state" field to the particle, or something similar,
        # so that each Slave task can access the state that is supposed to be
        # building up in the Kalman filter

        # Note that care needs to be taken in speculative methods to not
        # clobber the state that is passed around, or superfluously add to the
        # state when other particles are evaluating the motion, or when
        # speculative children are being moved.  This needs to be rethought to
        # be compatible with speculative evaluation.

        raise NotImplementedError("Kalman motion requires state that is not "
                "persistent in mrs")

        kalman = self.getfilter(particle, rand)

        grel = particle.nbestpos - particle.pos
        if self.norandscale:
            newvel = 1.0 * grel
        else:
            newvel = rand.uniform(0,2) * grel

        if self.restrictvel:
            self.cube.constrain_vec(newvel, True)

        newpos = particle.pos + newvel

        if not self.usepbest:
            kalman.add(newpos)
        else:
            kalman.add(array(list(newpos) + list(particle.pbestpos)))

        if self.predict:
            mean, var = kalman.predict()
        else:
            mean, var = kalman.filt()

        # Bad!  We should find a better way to initialize the random state
        # instead of just drawing a random number from the particle rand
        # This does give reproducible results, it just makes the random numbers
        # from state less good
        state = RandomState(rand.randint(0, sys.maxint))
        newstate = state.multivariate_normal(mean, var)
        return array(newstate[:self.dims]),array(newstate[self.dims:])


def ddot(*args):
    """multi-array dot product, done in order from left to right
    """
    return reduce(dot, args)


class KalmanFilter(object):
    def __init__(self, priors, priorvar, dynamics, dynamicvar, char, charvar):
        """Create a kalman filter object with an initial set of parameters.

        arguments:
            priors -- prior belief over system states (means vector)
            priorvar -- prior covariance matrix over system states
            dynamics -- matrix describing system dynamics, single step
            dynamicvar -- covariance matrix on dynamics
            char -- sensor characteristic matrix
            charvar -- covariance matrix on characteristics
        """

        num_states = len(dynamics)
        num_obs = len(char)

        # Pad the characteristic matrix in case it isn't already
        if num_obs != num_states and len(char[0]) != num_states:
            self.h = zeros((num_obs,num_states))
            carr = array( char ) * 1.0
            for row1, row2 in zip(self.h,carr):
                for i, x in enumerate(row2):
                    row1[i] = x
        else:
            self.h = 1.0 * array( char )

        # Set everything else up
        self.h_T = 1.0 * transpose( self.h )
        self.mu_t = 1.0 * array( priors )
        self.sig_t = 1.0 * array( priorvar )
        self.f = 1.0 * array( dynamics )
        self.f_T = 1.0 * transpose( self.f )
        self.sig_x = 1.0 * array( dynamicvar )
        self.sig_z = 1.0 * array( charvar )
        self.i = 1.0 * identity( len(priors ) )

    def add(self, observation):
        """Predicts the next state given the current observation.

        arguments:
            observation -- a vector of observation values
        """
        z = array(observation)

        ftf = ddot(self.f, self.sig_t, self.f_T)

        g1 = ddot(ftf + self.sig_x, self.h_T)
        g2 = inv(ddot(self.h, ftf + self.sig_x, self.h_T) + self.sig_z)
        gain = ddot(g1, g2)

        # Now we have the Kalman gain matrix.  With that, we calculate the
        # new mean and covariance matrices:
        mean = (ddot(self.f, self.mu_t) +
            ddot(gain, (z - ddot(self.h, self.f, self.mu_t))))

        cov = ddot(self.i - ddot(gain,self.h), ftf + self.sig_x)

        # Set the old values to the new values and return
        self.mu_t = mean
        self.sig_t = cov

    def filt(self):
        return self.mu_t, self.sig_t

    def predict(self):
        newmu = ddot(self.f, self.mu_t)
        newvar = self.sig_t

        return newmu, newvar

