"""Directional Statistics

Statistical distributions such as Von Mises--Fisher, Wishart, Bingham, etc.
"""

from __future__ import division, print_function

import itertools
import math
import scipy.optimize

try:
    import numpy as np
except ImportError:
    import numpypy as np

from . import linalg


##############################################################################
# Bingham Distribution

class BinghamSampler(object):
    """Sample from a real-valued Bingham distribution.

    The pdf is of the form:
        f(z) = c(A)^{-1} exp(x^T A x), x \in S^{k-1}

    where A is a k*k symmetric matrix, c(A) is a normalizing constant, and
    S^{k-1} is the unit sphere in R^k.

    Method from: Kume and Walker. Sampling from compositional and
    directional distributions.  Statistics and Computing, 2006.

    Parameters:
        lambdas: the first k-1 eigenvalues of -A (the smallest is assumed to
            be 0 and is not included in the list).
        smallest_eig: the smallest eigenvalue of -A before normalization
            (along with lambdas, this can be used to reconstruct the full list
            of eigenvalues).
    """
    def __init__(self, lambdas=None, eigvecs=None, smallest_eig=0):
        assert lambdas is not None and eigvecs is not None

        self._sampler = None
        self._eigvecs = eigvecs
        self.smallest_eig = smallest_eig
        self._lambdas = lambdas

        self._v = None
        self._w = None
        self._s = np.zeros(len(self._lambdas))

    def dual(self):
        """Return the Bingham(-A) sampler."""
        old_biggest_normalized = self._lambdas[0]
        smallest_eig = -(old_biggest_normalized + self.smallest_eig)

        lambdas = np.empty_like(self._lambdas)
        lambdas[0] = old_biggest_normalized
        lambdas[1:] = old_biggest_normalized - self._lambdas[:0:-1]

        eigvecs = np.array(self._eigvecs[::-1])
        return BinghamSampler(lambdas=lambdas, eigvecs=eigvecs,
                smallest_eig=smallest_eig)

    def sample(self, rand, thin=10):
        """Gibbs sampler iterator.

        Samples are thinned according to the given `thin` parameter.
        """
        # Note: we follow the Kent notation for indexing eigenvalues.
        # s_k = 1 - sum(s) and s_k corresponds to s_0 in the Kume paper.
        # Also, unlike the Kume paper, we assume all eigenvalues are unique.
        # The algorithm is much simpler without worrying about multiplicities.
        # Also note that the Kume paper is an awful paper (with a good idea),
        # so the formulas here look very different from their misleading junk.

        s = self._s

        for _ in range(thin):
            self._v = rand.uniform(0, math.exp(-sum(self._lambdas * s)))
            self._w = rand.uniform(0, (1 - sum(s)) ** (-0.5))

            for i, lambda_i in enumerate(self._lambdas):
                sum_of_others = sum(s[:i]) + sum(s[i+1:])
                c = max(0, 1 - self._w ** (-2) - sum_of_others)

                product_sum = (sum(self._lambdas[:i] * s[:i]) +
                        sum(self._lambdas[i+1:] * s[i+1:]))
                # Note: if lambda_i = 0, then the first term is float('inf'),
                # so in the end, d = 1 - sum_of_others.
                d = min((-math.log(self._v) - product_sum) / lambda_i,
                        1 - sum_of_others)

                # Note: there's an error in the Kume paper, which incorrectly
                # says to sample from: u = rand.uniform(c ** 2, d ** 2)
                u = rand.uniform(c ** 0.5, d ** 0.5)
                s[i] = u ** 2

        return self._convert_s_to_z(s)

    def _convert_s_to_z(self, s):
        """Convert a list of values on the simplex to values on the sphere."""
        z = np.empty(len(s) + 1)
        z[:-1] = s
        z[-1] = 1 - sum(s)
        z **= 0.5

        if self._eigvecs is not None:
            z = self._eigvecs.dot(z)
        return z

    def log_const(self):
        log_c = log_bingham_const(self._lambdas)

        # Note c(lambdas + h) = e^{-h} c(lambdas)
        log_c -= self.smallest_eig
        return log_c


def bingham_sampler_from_matrix(A):
    eigvals, eigvecs = linalg.eigh_swapped(-A)
    smallest_eig = eigvals[-1]
    lambdas = eigvals[:-1] - smallest_eig
    return BinghamSampler(lambdas, eigvecs, smallest_eig)


def log_bingham_const(lambdas):
    """Approximate the constant of integration of the Bingham density.

    The `lambdas` parameter refers to the shifted eigenvalues of -A, where A
    is the parameter of the Bingham distribution.  The smallest eigenvalue is
    assumed to be 0 and omitted.  Note that shifting the eigenvalues results
    in only a minor change to the Bingham constant: c(lambdas + h) = e^{-h}
    c(lambdas).

    See: Kume and Wood. Saddlepoint approximations for the Bingham and
    Fisher-Bingham normalising constants. Biometrika, 2005.
    """
    def cgf_prime_minus1(t):
        """First derivative of the cumulant generating function.

        See: Kume and Wood. Saddlepoint approximations for the Bingham and
        Fisher-Bingham normalising constants. Biometrika, 2005.
        """
        # Term for lambda_0 = 0:
        total = -0.5 / t
        for lambda_i in lambdas:
            total += 0.5 / (lambda_i - t)
        return total - 1

    def cgf_prime2(t):
        """Second derivative of the cumulant generating function.

        See: Kume and Wood. Saddlepoint approximations for the Bingham and
        Fisher-Bingham normalising constants. Biometrika, 2005.
        """
        # Term for lambda_0 = 0:
        total = 0.5 / t ** 2
        for lambda_i in lambdas:
            total += 0.5 / (lambda_i - t) ** 2
        return total

    # Find the solution to the saddlepoint equation K'_theta(t_hat)=1.
    x0 = -1 / 2
    t_hat = scipy.optimize.newton(cgf_prime_minus1, x0, fprime=cgf_prime2)
    assert t_hat < 0

    # Find various derivatives of the cumulant generating function at the
    # point t_hat.
    K_2_hat = cgf_prime2(t_hat)
    K_3_hat = -t_hat ** -3
    K_4_hat = 3 / t_hat ** 4
    for lambda_i in lambdas:
        K_3_hat += (lambda_i - t_hat) ** -3
        K_4_hat += 3 / (lambda_i - t_hat) ** 4

    # Find T, which appears in the formulas for the second-order
    # saddlepoint density approximations.
    rho_3_hat = K_3_hat / K_2_hat ** 1.5
    rho_4_hat = K_4_hat / K_2_hat ** 2
    T = rho_4_hat / 8 - (5 / 24) * rho_3_hat ** 2

    # Note that the (non-logspace) term for lambda_0 = 0 is (-t_hat)**-0.5.
    log_c_3 = (0.5 * (math.log(2) + len(lambdas) * math.log(math.pi))
            - 0.5 * math.log(-t_hat * K_2_hat)
            + T - t_hat)
    for lambda_i in lambdas:
        log_c_3 -= 0.5 * math.log(lambda_i - t_hat)
    return log_c_3


def log_bingham_const_eigvals(eigvals):
    """Approximate the constant of integration of the Bingham density."""
    argmin = eigvals.argmin()
    smallest_eig = eigvals[argmin]
    lambdas = eigvals[:-1] - smallest_eig
    if argmin != len(eigvals) - 1:
        lambdas[argmin] = eigvals[-1] - smallest_eig

    # Note c(lambdas + h) = e^{-h} c(lambdas)
    log_c = log_bingham_const(lambdas) - smallest_eig
    return log_c


def inverse_log_bingham_const(eigvals, target, index):
    """Find the inverse of the Bingham constant with respect to one element.

    Assumes that each eigenvalue will be positive.  In other words, it returns
    0 if the inverse is less than 0.

    The `index` parameter identifies the element.  The `target` parameter
    specifies the value of the Bingham constant.
    """
    # Note that the Bingham constant is monotone decreasing.
    eigvals = np.array(eigvals)
    def f(x):
        eigvals[index] = x
        return log_bingham_const_eigvals(eigvals) - target

    a = 0
    b = eigvals[index]
    if f(0) < 0:
        return 0

    while f(b) > 0:
        a = b
        b *= 2

    return scipy.optimize.brentq(f, a, b, xtol=1e-6)


class ComplexBinghamSampler(object):
    """Sample from a Complex Bingham distribution.

    The pdf is of the form:
        f(z) = c(A)^{-1} exp(z^T A z), z \in CS^{k-1}

    where A is a k*k symmetric matrix, c(A) is a normalizing constant, and
    CS^{k-1} is the unit sphere in C^k.

    Methods based on: Kent, Constable, and Er.  Simulation for the complex
    Bingham distribution.  Statistics and Computing, 2004.  We skip Method 3,
    which is only useful in very limited circumstances (all lambdas equal
    to about 0.5).

    Parameters (either A or lambdas must be specified, but not both):
        A: the parameter matrix of the Bingham distribution
        lambdas: the first k-1 eigenvalues of -A (the smallest is assumed to
            be 0 and is not included in the list).
    """
    def __init__(self, A=None, lambdas=None, eigvecs=None):
        assert A is None or (lambdas is None and eigvecs is None)

        self._sampler = None
        self._eigvecs = eigvecs

        if A is not None:
            eigvals, self._eigvecs = linalg.eigh_swapped(-A)
            smallest_eig = eigvals[-1]
            lambdas = eigvals[:-1] - smallest_eig
        self._lambdas = lambdas

    def dual(self):
        """Return the Bingham(-A) sampler."""
        # Eigenvalues of -A sorted largest to smallest.
        eigvals = np.append(-self._lambdas, 0.0)[::-1]
        smallest_eig = eigvals[-1]
        lambdas = eigvals[:-1] - smallest_eig
        eigvecs = np.array(self._eigvecs[::-1])
        return ComplexBinghamSampler(lambdas=lambdas, eigvecs=eigvecs)

    def _pick_sampler(self):
        if any(l == 0 for l in self._lambdas):
            return self.sample_m2

        k = len(self._lambdas) + 1

        # From Table 1: expected number for M1 with p_T removed.
        m1 = math.log(k - 1)
        for lambda_j in self._lambdas:
            m1 += math.log(1 - math.exp(-lambda_j))

        # From Table 1: expected number for M2 with p_T removed.
        m2 = math.log(k)
        for lambda_j in self._lambdas:
            m2 += math.log(lambda_j)
        m2 -= math.lgamma((k - 1) + 1)

        if m1 < m2:
            return self.sample_m1
        else:
            return self.sample_m2

    def sample(self, rand):
        if self._sampler is None:
            self._sampler = self._pick_sampler()
        return self._sampler(rand)

    def sample_m1(self, rand):
        """Sample using Method 1: Truncation to the simplex."""
        k = len(self._lambdas) + 1

        while True:
            uniforms = [rand.random() for _ in range(k - 1)]
            s = [-(1 / l_j) * math.log(1 - u_j * (1 - math.exp(-l_j)))
                for l_j, u_j in zip(self._lambdas, uniforms)]
            if sum(s) < 1:
                return self._convert_s_to_z(s)

    def sample_m2(self, rand):
        """Sample using Method 2: Acceptance-rejection on the simplex."""
        k = len(self._lambdas) + 1

        while True:
            uniforms = [rand.random() for _ in range(k - 1)]
            uniforms.sort()
            last = 0

            s = []
            for u in uniforms:
                s.append(u - last)
                last = u

            u = math.log(rand.random())
            if u < sum((-l_j * s_j) for l_j, s_j in zip(self._lambdas, s)):
                return self._convert_s_to_z(s)

    def _convert_s_to_z(self, s):
        """Convert a list of values on the simplex to values on the sphere."""
        s.append(1 - sum(s))
        s = np.array(s)
        z = s ** 0.5

        if self._eigvecs is not None:
            z = self._eigvecs.dot(z)
        return z


##############################################################################
# Directional Models

# NOTE: This model has problems.
class BinghamWishartModel(object):
    """A Wishart random variable with Bingham-distributed observations.

    The distribution of A is a Wishart parameterized by its inverse-scale
    matrix.  The inverse-scale parameter is constrained such that it must be
    positive definite and the angle of its first eigenvector from the x-axis
    must be less than pi/4.

    The prior distribution of A is...

    Note that k has an extremely skewed distribution, such that it makes more
    sense to use the maximum likelihood estimate of k than to sample from it
    (the probability of the second most likely value is 5 to 6 orders of
    magnitude smaller in some quick experiments).

    The failure Bingham distribution's parameter matrix is the Wishart prior,
    while the success Bingham distribution's parameter matrix is the negative
    of the Wishart prior.

    Attributes:
        inv_scale_L: the lower-triangular component of the Cholesky
            decomposition of the inverse of the scale matrix of the Wishart
            distribution
        dof: the degrees of freedom of the Wishart distribution
    """
    def __init__(self, inv_scale_L, dof):
        m, n = inv_scale_L.shape
        assert m == n

        self._inv_scale_L = inv_scale_L
        self._dims = n
        self._dof = dof

    def scale(self):
        """Give the scale matrix parameter of the Wishart distribution."""
        scale_L = np.linalg.inv(self._inv_scale_L)
        V = np.dot(scale_L, scale_L.T)
        return V

    def inv_scale(self):
        """Give the inverse scale matrix parameter of the Wishart."""
        return np.dot(self._inv_scale_L, self._inv_scale_L.T)

    def dual_inv(self):
        """Create a "dual" BinghamWishartModel.

        Note that there are many possible ways to define a dual.
        This finds the distribution whose scale parameter is the inverse of
        the current distribution's scale.
        """
        inv_scale_L = np.linalg.inv(self._inv_scale_L)
        return BinghamWishartModel(inv_scale_L, self._dof)

    def dual_reverse(self):
        """Create a "dual" BinghamWishartModel.

        Note that there are many possible ways to define a dual.
        This finds the distribution whose inv_scale matrix parameter's
        eigenvalues are "reversed".
        """
        old_eigvals, eigvecs = linalg.eigh_swapped(self.inv_scale())
        new_eigvals = old_eigvals[0] + old_eigvals[-1] - old_eigvals
        inv_scale = eigvecs.dot(np.diagflat(new_eigvals)).dot(eigvecs.T)
        inv_scale_L = np.linalg.cholesky(inv_scale)
        return BinghamWishartModel(inv_scale_L, self._dof)

    def incremented_dof(self, exp_scatter, n=1):
        """Create a new BinghamWishartModel with an incremented dof.

        The number of degrees of freedom is incremented by the given amount,
        and the prior scatter matrix is increased accordingly.
        """
        dof = self._dof + n
        inv_scale = self.inv_scale() + exp_scatter * n
        inv_scale_L = np.linalg.cholesky(inv_scale)
        return BinghamWishartModel(inv_scale_L, dof)

    def posterior_success(self, x):
        """Find the posterior given a sample from the success Bingham."""
        inv_scale_L = self._inv_scale_L.copy()
        dof = self._dof + 1

        chol_update(inv_scale_L, x)
        return BinghamWishartModel(inv_scale_L, dof)

    def posterior_failure(self, x):
        """Find the posterior given a sample from the success Bingham."""
        inv_scale_L = self._inv_scale_L.copy()
        dof = self._dof + 1

        chol_downdate(inv_scale_L, x)
        return BinghamWishartModel(inv_scale_L, dof)

    def sample_wishart(self, rand):
        """Sample from the Wishart distribution."""

        # Note that it's slightly faster for large (larger than 40x40)
        # matrices to use this instead:
        #   scipy.linalg.solve_triangular(R, np.identity(len(R)))
        # or even better: scipy.linalg.get_lapack_funcs('trtri') or something
        scale_L = np.linalg.inv(self._inv_scale_L)
        return sample_wishart(scale_L, self._dof, rand)

    def sample_success(self, rand, A=None):
        """Sample from the success Bingham distribution."""
        if A is None:
            A = self.sample_wishart(rand)
        bs = bingham_sampler_from_matrix(-A/2)
        return bs.sample(rand)

    def wishart_mean(self):
        """Expected Value of the Wishart distribution."""
        return self._dof * self.scale()

    def wishart_mode(self):
        """Mode of the Wishart distribution."""
        assert self._dof >= self._dims + 1
        return (self._dof - self._dims - 1) * self.scale()


def make_bingham_wishart_model(dims, kappa, rand):
    """Construct a new BinghamWishartModel with the given dimensions."""

    inv_scale_L = np.zeros((dims, dims))
    dof = 0

    exp_scatter = expected_mf_scatter(dims, kappa, rand)
    empty_model = BinghamWishartModel(inv_scale_L, dof)
    model = empty_model.incremented_dof(exp_scatter, dims)

    return model, exp_scatter


# NOTE: This model has problems.
class UnobservedBinghamWishartModel(object):
    """Bingham-Wishart Model without fully observed success/failure data.
    """
    def __init__(self, bingham_wishart, p_s, p_t_1, p_t_0):
        self._bingham_wishart = bingham_wishart
        self._bingham_wishart_dual = bingham_wishart.dual_reverse()

        self._log_p_s = math.log(p_s)
        self._log_q_s = math.log(1 - p_s)
        self._log_p_t_1 = math.log(p_t_1)
        self._log_q_t_1 = math.log(1 - p_t_1)
        self._log_p_t_0 = math.log(p_t_0)
        self._log_q_t_0 = math.log(1 - p_t_0)

        # Outcomes of imperfect success/failure tests: (x, t) pairs.
        self._observations = []
        # Current guesses of latent success/failure state.
        self._successes = []
        # Current sample from Wishart distribution
        self._A_sample = None
        self._A_dual_sample = None
        self._A_sample_log_const = None
        self._A_dual_sample_log_const = None

    def sample_success(self, rand):
        self.gibbs_wishart(rand)
        return self._bingham_wishart.sample_success(rand, self._A_sample)

    def record(self, x, t):
        """Record the outcome t of a test at direction x.

        Initially assumes that the latent state is `success`, since an invalid
        failure would cause inconsistency.  Thus, the `gibbs_successes`
        function should be called subsequently.
        """
        self._observations.append((x, t))
        self._successes.append(True)
        self._bingham_wishart = self._bingham_wishart.posterior_success(x)

    def gibbs_wishart(self, rand):
        """Sample from the Wishart distribution of node A."""
        self._A_sample = self._bingham_wishart.sample_wishart(rand)
        self._A_dual_sample = self._bingham_wishart_dual.sample_wishart(rand)
        bs = bingham_sampler_from_matrix(-self._A_sample / 2)
        bs_dual = bingham_sampler_from_matrix(-self._A_dual_sample / 2)
        self._A_sample_log_const = bs.log_const()
        self._A_dual_sample_log_const = bs_dual.log_const()
        print('lambdas:', bs._lambdas)
        print('smallest_eig:', bs.smallest_eig)
        print('dual lambdas:', bs_dual._lambdas)
        print('dual smallest_eig:', bs_dual.smallest_eig)

    def gibbs_successes(self, rand, n=None):
        """Sample from the complete conditional of a latent success state node.

        If an observation number `n` is not given, a random one is chosen.
        """
        if n is None:
            n = rand.randrange(len(self._observations))
        x, t = self._observations[n]

        A = self._A_sample
        A_dual = self._A_dual_sample
        xT_A_x = np.dot(x, np.dot(A, x))
        xT_A_dual_x = np.dot(x, np.dot(A_dual, x))

        log_p = self._log_p_s - xT_A_x / 2
        log_q = self._log_q_s - xT_A_dual_x / 2
        print()
        print()
        if t:
            print('T', end='')
            log_p += self._log_p_t_1
            log_q += self._log_q_t_1
        else:
            print('F', end='')
            log_p += self._log_p_t_0
            log_q += self._log_q_t_0
        print()
        print('x:', x)
        print('P_Bingham+:', math.exp(-xT_A_x / 2 - self._A_sample_log_const))
        print('P_Bingham-:', math.exp(xT_A_x / 2 - self._A_dual_sample_log_const))

        log_p -= self._A_sample_log_const
        log_q -= self._A_dual_sample_log_const

        log_C = ladd(log_p, log_q)
        log_p -= log_C
        log_q -= log_C
        print('P(+):', math.exp(log_p))
        print('P(-):', math.exp(log_q))

        success = (math.log(rand.random()) < log_p)
        if success == self._successes[n]:
            if success:
                print('(.)', end='')
            else:
                print('(_)', end='')
            return

        inv_scale_L = self._bingham_wishart._inv_scale_L.copy()
        dual_inv_scale_L = self._bingham_wishart_dual._inv_scale_L.copy()
        dof = self._bingham_wishart._dof
        dual_dof = self._bingham_wishart_dual._dof

        if success:
            chol_update(inv_scale_L, x)
            chol_downdate(dual_inv_scale_L, x)
            dof += 1
            dual_dof -= 1
            print('.', end='')
        else:
            chol_downdate(inv_scale_L, x)
            chol_update(dual_inv_scale_L, x)
            dof -= 1
            dual_dof += 1
            print('_', end='')

        self._bingham_wishart = BinghamWishartModel(inv_scale_L, dof)
        self._bingham_wishart_dual = BinghamWishartModel(dual_inv_scale_L,
                dual_dof)
        self._successes[n] = success


class BasicBinghamWishartModel(object):
    """The basic Bingham-Wishart Model (simple conjugate prior).

    A Wishart random variable with Bingham-distributed observations.

    The distribution of A is a Wishart parameterized by its inverse-scale
    matrix.  The inverse-scale parameter is constrained such that it must be
    positive definite and the angle of its first eigenvector from the x-axis
    must be less than pi/4.

    The prior distribution of A is...

    Note that k has an extremely skewed distribution, such that it makes more
    sense to use the maximum likelihood estimate of k than to sample from it
    (the probability of the second most likely value is 5 to 6 orders of
    magnitude smaller in some quick experiments).

    The Bingham distribution's parameter matrix is the negative of the Wishart
    prior.

    Attributes:
        inv_scale_L: the lower-triangular component of the Cholesky
            decomposition of the inverse of the scale matrix of the Wishart
            distribution
        dof: the degrees of freedom of the Wishart distribution
    """
    def __init__(self, inv_scale_L, dof):
        m, n = inv_scale_L.shape
        assert m == n

        self._inv_scale_L = inv_scale_L
        self._dims = n
        self._dof = dof

    def scale(self):
        """Give the scale matrix parameter of the Wishart distribution."""
        scale_L = np.linalg.inv(self._inv_scale_L)
        V = np.dot(scale_L, scale_L.T)
        return V

    def inv_scale(self):
        """Give the inverse scale matrix parameter of the Wishart."""
        return np.dot(self._inv_scale_L, self._inv_scale_L.T)

    def incremented_dof(self, exp_scatter, n=1):
        """Create a new BinghamWishartModel with an incremented dof.

        The number of degrees of freedom is incremented by the given amount,
        and the prior scatter matrix is increased accordingly.
        """
        dof = self._dof + n
        inv_scale = self.inv_scale() + exp_scatter * n
        inv_scale_L = np.linalg.cholesky(inv_scale)
        return BasicBinghamWishartModel(inv_scale_L, dof)

    def posterior_success(self, x):
        """Find the posterior given a sample from the success Bingham."""
        inv_scale_L = self._inv_scale_L.copy()
        dof = self._dof + 1

        linalg.chol_update(inv_scale_L, x)
        return BasicBinghamWishartModel(inv_scale_L, dof)

    def sample_wishart(self, rand):
        """Sample from the Wishart distribution."""

        # Note that it's slightly faster for large (larger than 40x40)
        # matrices to use this instead:
        #   scipy.linalg.solve_triangular(R, np.identity(len(R)))
        # or even better: scipy.linalg.get_lapack_funcs('trtri') or something
        scale_L = np.linalg.inv(self._inv_scale_L)
        return sample_wishart(scale_L, self._dof, rand)

    def sample_success(self, rand, A=None):
        """Sample from the success Bingham distribution."""
        if A is None:
            A = self.sample_wishart(rand)
        bs = bingham_sampler_from_matrix(-A/2)
        return bs.sample(rand)

    def wishart_mean(self):
        """Expected Value of the Wishart distribution."""
        return self._dof * self.scale()

    def wishart_mode(self):
        """Mode of the Wishart distribution."""
        assert self._dof >= self._dims + 1
        return (self._dof - self._dims - 1) * self.scale()


def make_basic_bingham_wishart_model(dims, kappa, dof, rand):
    """Construct a new BasicBinghamWishartModel with the given dimensions.

    The prior distribution is generated from the expected scatter matrix of a
    von Mises Fisher distribution centered at [1, 0, ..., 0] with
    concentration parameter `kappa` (the distribution tends to uniform as
    `kappa` approaches 0).  The `dof` parameter determines the number of
    pseudo-samples in the prior.
    """
    assert dof >= dims
    exp_scatter = expected_mf_scatter(dims, kappa, rand)
    empty_model = BasicBinghamWishartModel(np.zeros((dims, dims)), 0)
    model = empty_model.incremented_dof(exp_scatter, dof)

    return model


##############################################################################
# Wisham/Binghart/McNabb Distribution

from collections import defaultdict
accepts = defaultdict(int)
totals = defaultdict(int)
def wisham_binghart_sampler(inv_scale_L, dof, rand):
    """Sample from the conjugate prior of the Bingham distribution.

    Sampling technique uses Gibbs sampling.  Note that burn is not performed.
    """
    V = inv_scale_L.dot(inv_scale_L.T)
    V_eigs, _ = linalg.eigh_sorted(V)
    # Note that it's slightly faster for large (larger than 40x40)
    # matrices to use this instead:
    #   scipy.linalg.solve_triangular(R, np.identity(len(R)))
    # or even better: scipy.linalg.get_lapack_funcs('trtri') or something
    scale_L = np.linalg.inv(inv_scale_L)
    p, p2 = scale_L.shape
    assert p == p2

    v = np.empty((p, p))

    # Initialize the eigenvalues and eigenvectors.
    # Note that L is shaped as a 1-D array instead of as a matrix.
    L = None
    L, Q = linalg.eigh_sorted(scale_L.dot(scale_L.T))
    log_bing = log_bingham_const_eigvals(L)

    while True:
        # Sample from the auxiliary variables.

        # If U' ~ Uniform(0, B^{-n}) and if U = log(U'),
        # then U ~ -Exponential(1) - n log B
        #u = rand.uniform(0, math.exp(-dof * log_bing))
        log_u = -rand.expovariate(1) - dof * log_bing
        for i, eig_i in enumerate(L):
            for j, eig_j in enumerate(L):
                if j >= i:
                    break
                # Keeping v symmetric makes subsequent lookup easier.
                v[i, j] = v[j, i] = rand.uniform(0, abs(eig_i - eig_j))

        # Simulate from each of the eigenvalues.
        # TODO: it probably makes sense to randomize the ordering.
        for i, _ in enumerate(L):
            # Calculate the rate parameter of the exponential distribution.
            # Note: q_i^T (L L^T) q_i = (q_i^T L) (q_i^T L)^T
            # By the way, Q[i] and tmp are 1-D arrays, so they don't need to
            # be transposed before matrix multiplying.
            tmp = Q[i].dot(inv_scale_L)
            rate = tmp.dot(tmp)

            # Calculate the constraints on the support which are imposed by
            # the auxiliary variables.  The list of intervals represents
            # "banned" regions.
            inv_min = inverse_log_bingham_const(L, -log_u / dof, i)
            banned_intervals = [(-float('inf'), max(0, inv_min))]
            for j, eig_other in enumerate(L):
                if j == i:
                    continue
                radius = v[i, j]
                # The sampler is constrained to pick outside this interval.
                interval = (eig_other - radius, eig_other + radius)
                banned_intervals.append(interval)
            allowed_intervals = complement(banned_intervals)

            # Sample the eigenvalue from its full conditional.
            L[i] = sample_exp_intervals(rate, allowed_intervals, rand)

        log_bing = log_bingham_const_eigvals(L)
        for i, eig_i in enumerate(L):
            for j, eig_j in enumerate(L):
                if j >= i:
                    break
                assert abs(eig_i - eig_j) > v[i, j]
        assert log_u < -dof * log_bing

        # Simulate from the eigenvectors.
        # TODO: it probably makes sense to randomize the ordering.
        for i, eig_i in enumerate(L):
            for j, eig_j in enumerate(L):
                if j >= i:
                    break

                # TODO(?): try using sqrt(V_eigs[i] * V_eigs[j]) ???
                candsd = abs((eig_i - eig_j) * (V_eigs[i] - V_eigs[j])) ** -0.5
                # WARNING: MAGIC NUMBER
                #candsd *= 0.5
                candsd *= 2.0

                theta = rand.normalvariate(0, candsd)

                q_i = Q[i]
                q_j = Q[j]
                candq_i = math.cos(theta) * q_i + math.sin(theta) * q_j
                candq_j = -math.sin(theta) * q_i + math.cos(theta) * q_j

                # Note: 1-D arrays don't need to be transposed before matrix
                # multiplying.
                ratio = math.exp(
                    eig_i *
                        (q_i.dot(V).dot(q_i) - candq_i.dot(V).dot(candq_i))
                    - eig_j *
                        (q_j.dot(V).dot(q_j) - candq_j.dot(V).dot(candq_j))
                    )

                if rand.random() < ratio:
                    Q[i] = candq_i
                    Q[j] = candq_j
                    accepts[i, j] += 1
                totals[i, j] += 1
                #    print('A%s%s' % (i, j), end=' ')
                #else:
                #    print('R%s%s' % (i, j), end=' ')
        #print()

        yield np.array(L), np.array(Q)


def wisham_binghart_sampler_bad(inv_scale_L, dof, rand):
    """Sample from the conjugate prior of the Bingham distribution.

    Sampling technique uses Independent Metropolis Hastings with a Wishart
    proposal distribution.  Note that burn is not performed.
    """
    # Note that it's slightly faster for large (larger than 40x40)
    # matrices to use this instead:
    #   scipy.linalg.solve_triangular(R, np.identity(len(R)))
    # or even better: scipy.linalg.get_lapack_funcs('trtri') or something
    scale_L = np.linalg.inv(inv_scale_L)
    m, n = scale_L.shape
    assert m == n

    last = None
    last_b_const = None

    while True:
        cand = sample_wishart(2 * scale_L, m + 1, rand)

        eigvals, _ = np.linalg.eigh(cand)
        b_const = log_bingham_const_eigvals(eigvals)

        if last is None:
            accept = True
        else:
            log_prob = dof * (last_b_const - b_const)
            u = math.log(rand.random())
            accept = u < log_prob

        if accept:
            yield cand
            last = cand
            last_b_const = b_const
        else:
            yield last


def unionate(intervals):
    """Find the union of a set of closed intervals.

    A set of intervals is represented as a list of pairs.
    """
    if not intervals:
        return []
    intervals = list(intervals)
    intervals.sort()

    union = []
    a = b = None
    for next_a, next_b in intervals:
        if b is None:
            a, b = next_a, next_b
        elif next_a <= b:
            a, b = a, max(b, next_b)
        else:
            union.append((a, b))
            a, b = next_a, next_b
    union.append((a, b))

    return union


def complement(intervals):
    """Find a list of intervals that are the complement of the given intervals.
    """
    inf = float('inf')
    if not intervals:
        return [(-inf, inf)]
    banned_intervals = unionate(intervals)

    allowed_intervals = []
    # Flatten the list of intervals.
    points = list(itertools.chain.from_iterable(banned_intervals))

    if points[0] > -inf:
        allowed_intervals.append((-inf, points[0]))
    allowed_intervals.extend(zip(points[1::2], points[2::2]))
    if points[-1] < inf:
        allowed_intervals.append((points[-1], inf))

    return allowed_intervals


##############################################################################
# Wishart Distribution

def sample_wishart(scale_L, dof, rand):
    """Sample from a Wishart with the given scale and degrees of freedom.

    The scale matrix must be a positive definite.  If the scale matrix has
    dimension p, then the degrees of freedom must satisfy dof > p-1.

    Based on: Smith and Hocking. Wishart Variate Generator. 1972.
    """
    m, n = scale_L.shape
    A = np.zeros((m, n))
    for i in range(m):
        # The Chi-squared distribution is a special case of the Gamma
        # distribution.  Note that Python uses the scale parameterization
        # and that the paper uses 1-based instead of 0-based indexing.
        A[i, i] = rand.gammavariate((dof - i) / 2, 2) ** 0.5
    for i in range(1, m):
        for j in range(i):
            A[i, j] = rand.normalvariate(0, 1)
    LA = np.dot(scale_L, A)
    return np.dot(LA, LA.T)


##############################################################################
# Von Mises--Fisher Distribution

def sample_von_mises_fisher(dims, kappa, rand):
    """Samples from a von Mises Fisher distribution centered at [1, 0, ..., 0].

    To use a distribution at a different center, rotate the sample with a
    Householder transformation.
    """
    theta = rand.vonmisesvariate(0, kappa)
    head = np.array([math.cos(theta)])
    tail = math.sin(theta) * linalg.rand_norm_array(dims - 1, rand)
    return np.concatenate((head, tail))

def sample_mf_scatter(dims, kappa, num_samples, rand):
    """Sample from the scatter matrix of a set of von Mises Fisher samples.
    """
    samples = np.vstack([sample_von_mises_fisher(dims, kappa, rand)
            for _ in range(num_samples)])
    A = np.dot(samples.T, samples)
    return A

def expected_mf_scatter(dims, kappa, rand, samples=100000, step=1000):
    """Find the expected value of the scatter matrix of a von Mises Fisher.

    The von Mises Fisher distribution is centered at [1, 0, ..., 0] with
    concentration parameter `kappa` (the distribution tends to uniform as
    kappa approaches 0).

    The `rtol` parameter is the relative tolerance used in the stopping
    criterion.  The `step` parameter signifies how many von Mises Fisher
    samples to take at a time.

    Note that: Var(\sum{X_i} / n) = sigma^2 / n
        where sigma^2 is the variance of each independent X_i.
    So to divide the standard deviation by x, we need to multiply the number
    of samples by x^2.
    If the range of X_i is restricted to [0, 1] and its distribution is
    unimodal, then sigma^2 < 1/12.  This loose bound seems fairly effective
    at estimating the error of the diagonal entries in the scatter matrix.
    So samples=100000 gives almost four digits of accuracy.
    """
    assert samples % step == 0

    E = np.zeros((dims, dims))
    for _ in range(0, samples, step):
        A = sample_mf_scatter(dims, kappa, step, rand)

        E += A / samples

    # Average to reduce the total # of required samples.

    # Set indices for the diagonal (except the first entry).
    subdiag_rows, subdiag_cols = np.diag_indices(dims)
    subdiag_rows = subdiag_rows[1:]
    subdiag_cols = subdiag_cols[1:]

    # Set indices for the lower subtriangular entries (except the first col).
    subtril_rows, subtril_cols = np.tril_indices(dims - 2)
    subtril_rows = subtril_rows + 2
    subtril_cols = subtril_cols + 1
    subtriu_rows = dims - subtril_rows
    subtriu_cols = dims - subtril_cols

    # Average the first column (except the first entry).
    subcol1_mean = np.mean(E[1:, 0])
    E[1:, 0] = subcol1_mean
    E[0, 1:] = subcol1_mean
    # Average the diagonal (except the first entry).
    subdiag_mean = np.mean(E[subdiag_rows, subdiag_cols])
    E[subdiag_rows, subdiag_cols] = subdiag_mean
    # Average everything else.
    subtri_mean = np.mean(E[subtril_rows, subtril_cols])
    E[subtril_rows, subtril_cols] = subtri_mean
    E[subtriu_rows, subtriu_cols] = subtri_mean
    return E


##############################################################################
# Truncated Exponential Distribution

def sample_trunc_exp(rate, a, b, rand):
    r"""Sample from a Left- and Right-truncated Exponential distribution.

    The interval (a, b) bounds the distribution.  Note that due to the
    memorylessness of the distribution, setting a=0 is equivalent to a
    non-left-truncated distribution.

    f(x) = \frac{\lambda}{exp(-\lambda a) - exp(-\lambda b)} exp(-\lambda x)
    F(x) = (1 - exp(-\lambda (b - a))^{-1} (1 - exp(-\lambda (x - a)))
    F^{-1}(y) = a - \frac{1}{\lambda} log[1 - y (1 - exp(-\lambda (b - a)))]
    """
    c = math.exp(-rate * (b - a))
    return a - math.log(rand.uniform(c, 1)) / rate

def sample_exp_intervals(rate, intervals, rand):
    """Sample from an exponential that is constrained to a set of intervals."""
    pmf = []
    total = 0
    # Renormalize by the lowest value to avoid underflow issues.
    lowest = intervals[0][0]
    for a, b in intervals:
        a = a - lowest
        b = b - lowest
        mass = math.exp(-rate * a) - math.exp(-rate * b)
        pmf.append((mass, (a, b)))
        total += mass

    u = rand.uniform(0, total)
    for mass, (a, b) in pmf:
        u -= mass
        if u < 0:
            break

    assert a >= 0
    if b == float('inf'):
        return lowest + a + rand.expovariate(rate)
    else:
        return lowest + sample_trunc_exp(rate, a, b, rand)

##############################################################################
# Miscellaneous

def autocorr(samples):
    """Find the autocorrelation of a sequence of samples.

    This assumes that the samples are from a second-order stationary process.

    See the following links for more information:
    http://en.wikipedia.org/wiki/Autocorrelation
    http://stackoverflow.com/questions/12269834/is-there-any-numpy-autocorrellation-function-with-standardized-output
    http://stackoverflow.com/questions/643699/how-can-i-use-numpy-correlate-to-do-autocorrelation
    """
    samples = np.asarray(samples)
    centered = samples - np.mean(samples)
    full_corr = np.correlate(centered, centered, mode='full')
    center = full_corr.size / 2
    variance = full_corr[center]
    return full_corr[center:] / variance

# vim: et sw=4 sts=4
