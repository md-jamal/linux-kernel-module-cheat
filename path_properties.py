#!/usr/bin/env python3

import os

from shell_helpers import LF

class PathProperties:
    default_c_std = 'c11'
    default_cxx_std = 'c++17'
    default_properties = {
        'allowed_archs': None,
        'c_std': default_c_std,
        'cc_flags': [
            '-Wall', LF,
            '-Werror', LF,
            '-Wextra', LF,
            '-Wno-unused-function', LF,
            '-fopenmp', LF,
            '-ggdb3', LF,
        ],
        'cc_flags_after': [],
        'cc_pedantic': True,
        'cxx_std': default_cxx_std,
        'exit_status': 0,
        'extra_objs_baremetal_bootloader': False,
        # We should get rid of this if we ever properly implement dependency graphs.
        'extra_objs_lkmc_common': False,
        'extra_objs_userland_asm': False,
        'interactive': False,
        # The script takes a perceptible amount of time to run. Possibly an infinite loop.
        'more_than_1s': False,
        # The path should not be built. E.g., it is symlinked into multiple archs.
        'no_build': False,
        # The path does not generate an executable in itself, e.g.
        # it only generates intermediate object files. Therefore it
        # should not be run while testing.
        'no_executable': False,
        # the test receives a signal. We skip those tests for now,
        # on userland because we are lazy to figure out the exact semantics
        # of how Python + QEMU + gem5 determine the exit status of signals.
        'receives_signal': False,
        # The script requires a non-trivial argument to be passed to run properly.
        'requires_argument': False,
        # Requires certain of our custom kernel modules to be inserted to run.
        'requires_kernel_modules': False,
        # The example requires sudo, which usually implies that it can do something
        # deeply to the system it runs on, which would preventing further interactive
        # or test usage of the system, for example poweroff or messing up the GUI.
        'requires_sudo': False,
        # We were lazy to properly classify why we are skipping these tests.
        # TODO get it done.
        'skip_run_unclassified': False,
        'uses_dynamic_library': False,
    }

    '''
    Encodes properties of userland and baremetal paths.
    For directories, it applies to all files under the directory.
    Used to determine how to build and test the examples.
    '''
    def __init__(
        self,
        properties
    ):
        for key in properties:
            if not key in self.default_properties:
                raise ValueError('Unknown key: {}'.format(key))
        self.properties = properties.copy()

    def __getitem__(self, key):
        return self.properties[key]

    def __repr__(self):
        return str(self.properties)

    def set_path_components(self, path_components):
        self.path_components = path_components

    def should_be_built(self, env, link=False):
        if len(self.path_components) > 1 and \
                self.path_components[1] == 'libs' and \
                not env['package_all'] and \
                not self.path_components[2] in env['package']:
            return False
        return \
            not self['no_build'] and \
            (
                self['allowed_archs'] is None or
                env['arch'] in self['allowed_archs']
            ) and \
            not (
                link and
                self['no_executable']
            )

    def should_be_tested(self, env):
        return \
            self.should_be_built(env) and \
            not self['interactive'] and \
            not self['more_than_1s'] and \
            not self['no_executable'] and \
            not self['receives_signal'] and \
            not self['requires_argument'] and \
            not self['requires_kernel_modules'] and \
            not self['requires_sudo'] and \
            not self['skip_run_unclassified'] and \
            not (self['uses_dynamic_library'] and env['emulator'] == 'gem5')

    def update(self, other):
        other_tmp_properties = other.properties.copy()
        if 'cc_flags' in self.properties and 'cc_flags' in other_tmp_properties:
            other_tmp_properties['cc_flags'] = self.properties['cc_flags'] + other_tmp_properties['cc_flags']
        return self.properties.update(other_tmp_properties)

class PrefixTree:
    def __init__(self, path_properties_dict=None, children=None):
        if path_properties_dict is None:
            path_properties_dict = {}
        if children is None:
            children = {}
        self.children = children
        self.path_properties = PathProperties(path_properties_dict)

    @staticmethod
    def make_from_tuples(tuples):
        def tree_from_tuples(tuple_):
            if not type(tuple_) is tuple:
                tuple_ = (tuple_, {})
            cur_properties, cur_children = tuple_
            return PrefixTree(cur_properties, cur_children)
        top_tree = tree_from_tuples(tuples)
        todo_trees = [top_tree]
        while todo_trees:
            cur_tree = todo_trees.pop()
            cur_children = cur_tree.children
            for child_key in cur_children:
                new_tree = tree_from_tuples(cur_children[child_key])
                cur_children[child_key] = new_tree
                todo_trees.append(new_tree)
        return top_tree

def get(path):
    cur_node = path_properties_tree
    path_components = path.split(os.sep)
    path_properties = PathProperties(cur_node.path_properties.properties.copy())
    for path_component in path_components:
        if path_component in cur_node.children:
            cur_node = cur_node.children[path_component]
            path_properties.update(cur_node.path_properties)
        else:
            break
    path_properties.set_path_components(path_components)
    return path_properties

gnu_extension_properties = {
    'c_std': 'gnu11',
    'cc_pedantic': False,
    'cxx_std': 'gnu++17'
}
freestanding_properties = {
    'cc_flags': [
        '-ffreestanding', LF,
        '-nostdlib', LF,
        '-static', LF,
    ],
    'extra_objs_userland_asm': False,
}
# See: https://github.com/cirosantilli/linux-kernel-module-cheat#user-mode-simulation-path_properties
path_properties_tuples = (
    PathProperties.default_properties,
    {
        'baremetal': (
            {},
            {
                'arch': (
                    {},
                    {
                        'arm': (
                            {'allowed_archs': {'arm'}},
                            {
                                'no_bootloader': {'extra_objs_baremetal_bootloader': False},
                            },
                        ),
                        'aarch64': (
                            {'allowed_archs': {'aarch64'}},
                            {
                                'no_bootloader': {'extra_objs_baremetal_bootloader': False},
                            },
                        )
                    }
                ),
                'assert_fail.c': {'exit_status': 1},
                'exit1.c': {'exit_status': 1},
                'infinite_loop.c': {'more_than_1s': True},
                'lib': (
                    {'no_executable': True},
                    {}
                ),
                'getchar.c': {'interactive': True},
                'return1.c': {'exit_status': 1},
            }
        ),
        'userland': (
            {
                'cc_flags_after': [
                    '-lm', LF,
                    '-pthread', LF,
                ],
            },
            {
                'arch': (
                    {
                        'cc_flags': [
                            '-fno-pie', LF,
                            '-no-pie', LF,
                        ],
                        'extra_objs_userland_asm': True,
                    },
                    {
                        'arm': (
                            {
                                'allowed_archs': {'arm'},
                                'cc_flags': [
                                    '-Xassembler', '-mcpu=cortex-a72', LF,
                                    # To prevent:
                                    # > vfp.S: Error: selected processor does not support <FPU instruction> in ARM mode
                                    # https://stackoverflow.com/questions/41131432/cross-compiling-error-selected-processor-does-not-support-fmrx-r3-fpexc-in/52875732#52875732
                                    # We aim to take the most extended mode currently available that works on QEMU.
                                    '-Xassembler', '-mfpu=crypto-neon-fp-armv8.1', LF,
                                    '-Xassembler', '-meabi=5', LF,
                                    # Treat inline assembly as arm instead of thumb
                                    # The opposite of -mthumb.
                                    '-marm', LF,
                                    # Make gcc generate .syntax unified for inline assembly.
                                    # However, it gets ignored if -marm is given, which a GCC bug that was recently fixed:
                                    # https://stackoverflow.com/questions/54078112/how-to-write-syntax-unified-ual-armv7-inline-assembly-in-gcc/54132097#54132097
                                    # So we just write divided inline assembly for now.
                                    '-masm-syntax-unified', LF,
                                ]
                            },
                            {
                                'c': (
                                    {
                                        'extra_objs_userland_asm': False,
                                    },
                                    {
                                        'freestanding': freestanding_properties,
                                    },
                                ),
                                'freestanding': freestanding_properties,
                            }
                        ),
                        'aarch64': (
                            {'allowed_archs': {'aarch64'}},
                            {
                                'c': (
                                    {
                                        'extra_objs_userland_asm': False,
                                    },
                                    {
                                        'freestanding': freestanding_properties,
                                    },
                                ),
                                'freestanding': freestanding_properties,
                            }
                        ),
                        'empty.S': {'no_build': True},
                        'fail.S': {'no_build': True},
                        'main.c': {
                            'extra_objs_userland_asm': False,
                            'no_executable': True
                        },
                        'x86_64': (
                            {'allowed_archs': {'x86_64'}},
                            {
                                'c': (
                                    {
                                        'extra_objs_userland_asm': False,
                                    },
                                    {
                                        'freestanding': freestanding_properties,
                                        'ring0.c': {'receives_signal': True}
                                    }
                                ),
                                'freestanding': freestanding_properties,
                            }
                        ),
                    }
                ),
                'c': (
                    {},
                    {
                        'false.c': {'exit_status': 1},
                        'getchar.c': {'interactive': True},
                        'infinite_loop.c': {'more_than_1s': True},
                    }
                ),
                'gcc': gnu_extension_properties,
                'kernel_modules': {**gnu_extension_properties, **{'requires_kernel_modules': True}},
                'lkmc': (
                    {'extra_objs_lkmc_common': True},
                    {
                        'assert_fail.c': {'exit_status': 1},
                    }
                ),
                'libs': (
                    {'uses_dynamic_library': True},
                    {
                        'libdrm': {'requires_sudo': True},
                    }
                ),
                'linux': (
                    gnu_extension_properties,
                    {
                        'ctrl_alt_del.c': {'requires_sudo': True},
                        'init_env_poweroff.c': {'requires_sudo': True},
                        'myinsmod.c': {'requires_sudo': True},
                        'myrmmod.c': {'requires_sudo': True},
                        'pagemap_dump.c': {'requires_argument': True},
                        'poweroff.c': {'requires_sudo': True},
                        'proc_events.c': {'requires_sudo': True},
                        'proc_events.c': {'requires_sudo': True},
                        'sched_getaffinity_threads.c': {'more_than_1s': True},
                        'time_boot.c': {'requires_sudo': True},
                        'virt_to_phys_user.c': {'requires_argument': True},
                    }
                ),
                'posix': (
                    {},
                    {
                        'count.c': {'more_than_1s': True},
                        'sleep_forever.c': {'more_than_1s': True},
                        'virt_to_phys_test.c': {'more_than_1s': True},
                    }
                ),
            }
        ),
    }
)
path_properties_tree = PrefixTree.make_from_tuples(path_properties_tuples)
