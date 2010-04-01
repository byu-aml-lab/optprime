#!/usr/bin/env python
from __future__ import division

BATCHES = 4

PARTICLES = [5, 50, 500, 5000]
FUNCTION = 'sphere.Sphere'
DIMS = 50
TOPOLOGY = 'Ring'
NEIGHBORS_PROPORTION = 0.05
MIN_ITERS = 5000
MIN_EVALS = 25000000
OUTFREQ_EVALS = 100

import math
import os
import subprocess
import tempfile

NEIGHBORLESS_TOPOLOGIES = ('Complete',)
shortfunc = FUNCTION.split('.')[-1]


for particles in PARTICLES:
    iters = max(MIN_ITERS, int(math.ceil(MIN_EVALS / particles)))
    neighbors = int(math.ceil(NEIGHBORS_PROPORTION * particles))
    #neighbors = int(math.ceil(math.log(particles)))
    outfreq = int(math.ceil(OUTFREQ_EVALS / particles))
    if TOPOLOGY in NEIGHBORLESS_TOPOLOGIES:
        datadir = os.path.expanduser('~/clone/psodata/data_%s_%s/%s_%s'
                % (shortfunc, DIMS, TOPOLOGY, particles))
    else:
        datadir = os.path.expanduser('~/clone/psodata/data_%s_%s/%s_%s_%s'
                % (shortfunc, DIMS, TOPOLOGY, particles, neighbors))
    template = 'iters_%s_freq_%s' % (iters, outfreq)
    try:
        os.makedirs(datadir)
    except OSError:
        pass
    for i in xrange(BATCHES):
        proc = subprocess.Popen(('batch',), stdin=subprocess.PIPE)
        proc.stdin.write('FILENAME="$(mktemp --tmpdir=%s %s.XXX)"\n'
                % (datadir, template))
        proc.stdin.write('cd ~/clone/amlpso\n')
        proc.stdin.write('pwd\n')
        if TOPOLOGY in NEIGHBORLESS_TOPOLOGIES:
            proc.stdin.write('python standardpso.py -i %s --out-freq=%s'
                ' -f %s -d %s -t %s -n %s >"$FILENAME"\n'
                % (iters, outfreq, FUNCTION, DIMS, TOPOLOGY, particles))
        else:
            proc.stdin.write('python standardpso.py -i %s --out-freq=%s'
                ' -f %s -d %s -t %s -n %s --top-neighbors %s >"$FILENAME"\n'
                % (iters, outfreq, FUNCTION, DIMS, TOPOLOGY, particles,
                    neighbors))
        proc.stdin.close()
        proc.wait()


# vim: et sw=4 sts=4
