#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2013-2015 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2013 Stefano Maggiolo <s.maggiolo@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""A Job is an abstraction of an "atomic" action of a Worker.

Jobs play a major role in the interface with TaskTypes: they are a
data structure containing all information about what the TaskTypes
should do. They are mostly used in the communication between ES and
the Workers, hence they contain only serializable data (for example,
the name of the task type, not the task type object itself).

A Job represents an indivisible action of a Worker, for example
"compile the submission" or "evaluate the submission on a certain
testcase".

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import json

from cms.db import File, Manager, Executable, UserTestExecutable, Evaluation


class Job(object):
    """Base class for all jobs.

    Input data (usually filled by ES): task_type,
    task_type_parameters. Metadata: shard, sandboxes, info.

    """

    # TODO Move 'success' inside Job.

    def __init__(self, task_type=None, task_type_parameters=None,
                 shard=None, sandboxes=None, info=None):
        """Initialization.

        task_type (string|None): the name of the task type.
        task_type_parameters (string|None): the parameters for the
            creation of the correct task type.
        shard (int|None): the shard of the Worker completing this job.
        sandboxes ([string]|None): the paths of the sandboxes used in
            the Worker during the execution of the job.
        info (string|None): a human readable description of the job.

        """
        if task_type is None:
            task_type = ""
        if task_type_parameters is None:
            task_type_parameters = []
        if sandboxes is None:
            sandboxes = []
        if info is None:
            info = ""

        self.task_type = task_type
        self.task_type_parameters = task_type_parameters
        self.shard = shard
        self.sandboxes = sandboxes
        self.info = info

    def export_to_dict(self):
        res = {
            'task_type': self.task_type,
            'task_type_parameters': self.task_type_parameters,
            'shard': self.shard,
            'sandboxes': self.sandboxes,
            'info': self.info,
            }
        return res

    @staticmethod
    def import_from_dict_with_type(data):
        type_ = data['type']
        del data['type']
        if type_ == 'compilation':
            return CompilationJob.import_from_dict(data)
        elif type_ == 'evaluation':
            return EvaluationJob.import_from_dict(data)
        else:
            raise Exception("Couldn't import dictionary with type %s" %
                            (type_))

    @classmethod
    def import_from_dict(cls, data):
        return cls(**data)


class CompilationJob(Job):
    """Job representing a compilation.

    Can represent either the compilation of a user test, or of a
    submission, or of an arbitrary source (as used in cmsMake).

    Input data (usually filled by ES): language, files,
    managers. Output data (filled by the Worker): success,
    compilation_success, executables, text, plus.

    """

    def __init__(self, task_type=None, task_type_parameters=None,
                 shard=None, sandboxes=None, info=None,
                 language=None, files=None, managers=None,
                 success=None, compilation_success=None,
                 executables=None, text=None, plus=None):
        """Initialization.

        See base class for the remaining arguments.

        language (string|None): the language of the submission / user
            test.
        files ({string: File}|None): files submitted by the user.
        managers ({string: Manager}|None): managers provided by the
            admins.
        success (bool|None): whether the job succeeded.
        compilation_success (bool|None): whether the compilation implicit
            in the job succeeded, or there was a compilation error.
        executables ({string: Executable}|None): executables created
            in the job.
        text ([object]|None): description of the outcome of the job,
            to be presented to the user. The first item is a string,
            potentially with %-escaping; the following items are the
            values to be %-formatted into the first.
        plus ({}|None): additional metadata.

        """
        if files is None:
            files = {}
        if managers is None:
            managers = {}
        if executables is None:
            executables = {}

        Job.__init__(self, task_type, task_type_parameters,
                     shard, sandboxes, info)
        self.language = language
        self.files = files
        self.managers = managers
        self.success = success
        self.compilation_success = compilation_success
        self.executables = executables
        self.text = text
        self.plus = plus

    def export_to_dict(self):
        res = Job.export_to_dict(self)
        res.update({
            'type': 'compilation',
            'language': self.language,
            'files': dict((k, v.digest)
                          for k, v in self.files.iteritems()),
            'managers': dict((k, v.digest)
                             for k, v in self.managers.iteritems()),
            'success': self.success,
            'compilation_success': self.compilation_success,
            'executables': dict((k, v.digest)
                                for k, v in self.executables.iteritems()),
            'text': self.text,
            'plus': self.plus,
            })
        return res

    @classmethod
    def import_from_dict(cls, data):
        data['files'] = dict(
            (k, File(k, v)) for k, v in data['files'].iteritems())
        data['managers'] = dict(
            (k, Manager(k, v)) for k, v in data['managers'].iteritems())
        data['executables'] = dict(
            (k, Executable(k, v)) for k, v in data['executables'].iteritems())
        return cls(**data)

    @staticmethod
    def from_submission(submission, dataset):
        job = CompilationJob()

        # Job
        job.task_type = dataset.task_type
        job.task_type_parameters = dataset.task_type_parameters

        # CompilationJob; dict() is required to detach the dictionary
        # that gets added to the Job from the control of SQLAlchemy
        job.language = submission.language
        job.files = dict(submission.files)
        job.managers = dict(dataset.managers)
        job.info = "compile submission %d" % (submission.id)

        return job

    def to_submission(self, sr):
        # This should actually be useless.
        sr.invalidate_compilation()

        # No need to check self.success because this method gets called
        # only if it is True.

        sr.set_compilation_outcome(self.compilation_success)
        sr.compilation_text = json.dumps(self.text, encoding='utf-8')
        sr.compilation_stdout = self.plus.get('stdout')
        sr.compilation_stderr = self.plus.get('stderr')
        sr.compilation_time = self.plus.get('execution_time')
        sr.compilation_wall_clock_time = \
            self.plus.get('execution_wall_clock_time')
        sr.compilation_memory = self.plus.get('execution_memory')
        sr.compilation_shard = self.shard
        sr.compilation_sandbox = ":".join(self.sandboxes)
        for executable in self.executables.itervalues():
            sr.executables += [executable]

    @staticmethod
    def from_user_test(user_test, dataset):
        job = CompilationJob()

        # Job
        job.task_type = dataset.task_type
        job.task_type_parameters = dataset.task_type_parameters

        # CompilationJob; dict() is required to detach the dictionary
        # that gets added to the Job from the control of SQLAlchemy
        job.language = user_test.language
        job.files = dict(user_test.files)
        job.managers = dict(user_test.managers)
        job.info = "compile user test %d" % (user_test.id)

        # Add the managers to be got from the Task; get_task_type must
        # be imported here to avoid circular dependencies
        from cms.grading.tasktypes import get_task_type
        task_type = get_task_type(dataset=dataset)
        auto_managers = task_type.get_auto_managers()
        if auto_managers is not None:
            for manager_filename in auto_managers:
                job.managers[manager_filename] = \
                    dataset.managers[manager_filename]
        else:
            for manager_filename in dataset.managers:
                if manager_filename not in job.managers:
                    job.managers[manager_filename] = \
                        dataset.managers[manager_filename]

        return job

    def to_user_test(self, ur):
        # This should actually be useless.
        ur.invalidate_compilation()

        # No need to check self.success because this method gets called
        # only if it is True.

        ur.set_compilation_outcome(self.compilation_success)
        ur.compilation_text = json.dumps(self.text, encoding='utf-8')
        ur.compilation_stdout = self.plus.get('stdout')
        ur.compilation_stderr = self.plus.get('stderr')
        ur.compilation_time = self.plus.get('execution_time')
        ur.compilation_wall_clock_time = \
            self.plus.get('execution_wall_clock_time')
        ur.compilation_memory = self.plus.get('execution_memory')
        ur.compilation_shard = self.shard
        ur.compilation_sandbox = ":".join(self.sandboxes)
        for executable in self.executables.itervalues():
            u_executable = UserTestExecutable(
                executable.filename, executable.digest)
            ur.executables += [u_executable]


class EvaluationJob(Job):
    """Job representing an evaluation on a testcase.

    Can represent either the evaluation of a user test, or of a
    submission, or of an arbitrary source (as used in cmsMake).

    Input data (usually filled by ES): testcase_codename, language,
    files, managers, executables, input, output, time_limit,
    memory_limit. Output data (filled by the Worker): success,
    outcome, text, user_output, executables, text, plus. Metadata:
    only_execution, get_output.

    """
    def __init__(self, task_type=None, task_type_parameters=None,
                 shard=None, sandboxes=None, info=None,
                 testcase_codename=None, language=None,
                 files=None, managers=None, executables=None,
                 input=None, output=None,
                 time_limit=None, memory_limit=None,
                 success=None, outcome=None, text=None,
                 user_output=None, plus=None,
                 only_execution=False, get_output=False):
        """Initialization.

        See base class for the remaining arguments.

        testcase_codename (string|None): the codename of the testcase
            this is an evaluation for.
        language (string|None): the language of the submission or user
            test.
        files ({string: File}|None): files submitted by the user.
        managers ({string: Manager}|None): managers provided by the
            admins.
        executables ({string: Executable}|None): executables created
            in the compilation.
        input (string|None): digest of the input file.
        output (string|None): digest of the output file.
        time_limit (float|None): user time limit in seconds.
        memory_limit (int|None): memory limit in bytes.
        success (bool|None): whether the job succeeded.
        outcome (string|None): the outcome of the evaluation, from
            which to compute the score.
        text ([object]|None): description of the outcome of the job,
            to be presented to the user. The first item is a string,
            potentially with %-escaping; the following items are the
            values to be %-formatted into the first.
        user_output (unicode|None): if requested (with get_output),
            the digest of the file containing the output of the user
            program.
        plus ({}|None): additional metadata.
        only_execution (bool|None): whether to perform only the
            execution, or to compare the output with the reference
            solution too.
        get_output (bool|None): whether to retrieve the execution
            output (together with only_execution, useful for the user
            tests).

        """
        if files is None:
            files = {}
        if managers is None:
            managers = {}
        if executables is None:
            executables = {}

        Job.__init__(self, task_type, task_type_parameters,
                     shard, sandboxes, info)
        self.testcase_codename = testcase_codename
        self.language = language
        self.files = files
        self.managers = managers
        self.executables = executables
        self.input = input
        self.output = output
        self.time_limit = time_limit
        self.memory_limit = memory_limit
        self.success = success
        self.outcome = outcome
        self.text = text
        self.user_output = user_output
        self.plus = plus
        self.only_execution = only_execution
        self.get_output = get_output

    def export_to_dict(self):
        res = Job.export_to_dict(self)
        res.update({
            'type': 'evaluation',
            'testcase_codename': self.testcase_codename,
            'language': self.language,
            'files': dict((k, v.digest)
                          for k, v in self.files.iteritems()),
            'managers': dict((k, v.digest)
                             for k, v in self.managers.iteritems()),
            'executables': dict((k, v.digest)
                                for k, v in self.executables.iteritems()),
            'input': self.input,
            'output': self.output,
            'time_limit': self.time_limit,
            'memory_limit': self.memory_limit,
            'success': self.success,
            'outcome': self.outcome,
            'text': self.text,
            'user_output': self.user_output,
            'plus': self.plus,
            'only_execution': self.only_execution,
            'get_output': self.get_output,
            })
        return res

    @classmethod
    def import_from_dict(cls, data):
        data['files'] = dict(
            (k, File(k, v)) for k, v in data['files'].iteritems())
        data['managers'] = dict(
            (k, Manager(k, v)) for k, v in data['managers'].iteritems())
        data['executables'] = dict(
            (k, Executable(k, v)) for k, v in data['executables'].iteritems())
        return cls(**data)

    @staticmethod
    def from_submission(submission, dataset, testcase_codename):
        job = EvaluationJob()

        # Job
        job.task_type = dataset.task_type
        job.task_type_parameters = dataset.task_type_parameters

        submission_result = submission.get_result(dataset)

        # This should have been created by now.
        assert submission_result is not None

        # EvaluationJob; dict() is required to detach the dictionary
        # that gets added to the Job from the control of SQLAlchemy
        job.testcase_codename = testcase_codename
        job.language = submission.language
        job.files = dict(submission.files)
        job.managers = dict(dataset.managers)
        job.executables = dict(submission_result.executables)
        job.time_limit = dataset.time_limit
        job.memory_limit = dataset.memory_limit

        testcase = dataset.testcases[testcase_codename]
        job.input = testcase.input
        job.output = testcase.output
        job.info = "evaluate submission %d on testcase %s" % \
                   (submission.id, testcase.codename)

        return job

    def to_submission(self, sr):
        # Should not invalidate because evaluations will be added one
        # by one now.

        # No need to check self.success because this method gets called
        # only if it is True.

        sr.evaluations += [Evaluation(
            text=json.dumps(self.text, encoding='utf-8'),
            outcome=self.outcome,
            execution_time=self.plus.get('execution_time'),
            execution_wall_clock_time=self.plus.get(
                'execution_wall_clock_time'),
            execution_memory=self.plus.get('execution_memory'),
            evaluation_shard=self.shard,
            evaluation_sandbox=":".join(self.sandboxes),
            testcase=sr.dataset.testcases[self.testcase_codename])]

    @staticmethod
    def from_user_test(user_test, dataset):
        job = EvaluationJob()

        # Job
        job.task_type = dataset.task_type
        job.task_type_parameters = dataset.task_type_parameters

        user_test_result = user_test.get_result(dataset)

        # This should have been created by now.
        assert user_test_result is not None

        # EvaluationJob; dict() is required to detach the dictionary
        # that gets added to the Job from the control of SQLAlchemy
        job.testcase_codename = None
        job.language = user_test.language
        job.files = dict(user_test.files)
        job.managers = dict(user_test.managers)
        job.executables = dict(user_test_result.executables)
        job.input = user_test.input
        job.time_limit = dataset.time_limit
        job.memory_limit = dataset.memory_limit
        job.info = "evaluate user test %d" % (user_test.id)

        # Add the managers to be got from the Task; get_task_type must
        # be imported here to avoid circular dependencies
        from cms.grading.tasktypes import get_task_type
        task_type = get_task_type(dataset=dataset)
        auto_managers = task_type.get_auto_managers()
        if auto_managers is not None:
            for manager_filename in auto_managers:
                job.managers[manager_filename] = \
                    dataset.managers[manager_filename]
        else:
            for manager_filename in dataset.managers:
                if manager_filename not in job.managers:
                    job.managers[manager_filename] = \
                        dataset.managers[manager_filename]

        job.get_output = True
        job.only_execution = True

        return job

    def to_user_test(self, ur):
        # This should actually be useless.
        ur.invalidate_evaluation()

        # No need to check self.success because this method gets called
        # only if it is True.

        ur.evaluation_text = json.dumps(self.text, encoding='utf-8')
        ur.set_evaluation_outcome()
        ur.execution_time = self.plus.get('execution_time')
        ur.execution_wall_clock_time = \
            self.plus.get('execution_wall_clock_time')
        ur.execution_memory = self.plus.get('execution_memory')
        ur.evaluation_shard = self.shard
        ur.evaluation_sandbox = ":".join(self.sandboxes)
        ur.output = self.user_output
