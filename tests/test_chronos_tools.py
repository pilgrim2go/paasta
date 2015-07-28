import contextlib

import mock
from pytest import raises

import chronos_tools


class TestChronosTools:

    fake_service_name = 'test_service'
    fake_cluster = 'penguin'
    fake_config_dict = {
        'name': 'test',
        'description': 'This is a test Chronos job.',
        'command': '/bin/sleep 40',
        'epsilon': 'PT30M',
        'retries': 5,
        'owner': 'test@test.com',
        'async': False,
        'cpus': 5.5,
        'mem': 1024.4,
        'disk': 2048.5,
        'disabled': 'true',
        'schedule': 'R/2015-03-25T19:36:35Z/PT5M',
        'schedule_time_zone': 'Zulu',
    }
    fake_branch_dict = {
        'full_branch': 'paasta-%s-%s' % (fake_service_name, fake_cluster),
    }
    fake_chronos_job_config = chronos_tools.ChronosJobConfig(fake_service_name, fake_config_dict, fake_branch_dict)

    fake_invalid_config_dict = {
        'epsilon': 'nolispe',
        'retries': 5.7,
        'async': True,
        'cpus': 'intel',
        'mem': 'lots',
        'disk': 'all of it',
        'schedule': 'forever/now/5 min',
        'schedule_time_zone': '+0200',
    }
    fake_invalid_chronos_job_config = chronos_tools.ChronosJobConfig(fake_service_name,
                                                                     fake_invalid_config_dict,
                                                                     fake_branch_dict)

    def test_load_chronos_job_config(self):
        fake_soa_dir = '/tmp/'
        expected_chronos_conf_file = 'chronos-penguin'
        with contextlib.nested(
            mock.patch('service_configuration_lib.read_extra_service_information', autospec=True),
        ) as (
            mock_read_extra_service_information,
        ):
            mock_read_extra_service_information.return_value = self.fake_config_dict
            actual = chronos_tools.load_chronos_job_config(self.fake_service_name, self.fake_cluster, fake_soa_dir)
            mock_read_extra_service_information.assert_called_once_with(self.fake_service_name,
                                                                        expected_chronos_conf_file,
                                                                        soa_dir=fake_soa_dir)
            assert actual == self.fake_chronos_job_config

    def test_get_config_dict_param(self):
        param = 'epsilon'
        expected = 'PT30M'
        actual = self.fake_chronos_job_config.get(param)
        assert actual == expected

    def test_get_branch_dict_param(self):
        param = 'full_branch'
        expected = 'paasta-test_service-penguin'
        actual = self.fake_chronos_job_config.get(param)
        assert actual == expected

    def test_get_service_name(self):
        param = 'service_name'
        expected = 'test_service'
        actual = self.fake_chronos_job_config.get(param)
        assert actual == expected

    def test_get_unknown_param(self):
        param = 'mainframe'
        actual = self.fake_chronos_job_config.get(param)
        assert actual is None

    def test_check_epsilon_valid(self):
        okay, msg = self.fake_chronos_job_config.check_epsilon()
        assert okay is True
        assert msg == ''

    def test_check_epsilon_invalid(self):
        okay, msg = self.fake_invalid_chronos_job_config.check_epsilon()
        assert okay is False
        assert msg == 'The specified epsilon value \'nolispe\' does not conform to the ISO8601 format.'

    def test_check_retries_valid(self):
        okay, msg = self.fake_chronos_job_config.check_retries()
        assert okay is True
        assert msg == ''

    def test_check_retries_invalid(self):
        okay, msg = self.fake_invalid_chronos_job_config.check_retries()
        assert okay is False
        assert msg == 'The specified retries value \'5.7\' is not a valid int.'

    def test_check_async_valid(self):
        okay, msg = self.fake_chronos_job_config.check_async()
        assert okay is True
        assert msg == ''

    def test_check_async_invalid(self):
        okay, msg = self.fake_invalid_chronos_job_config.check_async()
        assert okay is False
        assert msg == 'The config specifies that the job is async, which we don\'t support.'

    def test_check_cpus_valid(self):
        okay, msg = self.fake_chronos_job_config.check_cpus()
        assert okay is True
        assert msg == ''

    def test_check_cpus_invalid(self):
        okay, msg = self.fake_invalid_chronos_job_config.check_cpus()
        assert okay is False
        assert msg == 'The specified cpus value \'intel\' is not a valid float.'

    def test_check_mem_valid(self):
        okay, msg = self.fake_chronos_job_config.check_mem()
        assert okay is True
        assert msg == ''

    def test_check_mem_invalid(self):
        okay, msg = self.fake_invalid_chronos_job_config.check_mem()
        assert okay is False
        assert msg == 'The specified mem value \'lots\' is not a valid float.'

    def test_check_disk_valid(self):
        okay, msg = self.fake_chronos_job_config.check_disk()
        assert okay is True
        assert msg == ''

    def test_check_disk_invalid(self):
        okay, msg = self.fake_invalid_chronos_job_config.check_disk()
        assert okay is False
        assert msg == 'The specified disk value \'all of it\' is not a valid float.'

    def test_check_schedule_repeat_helper_valid(self):
        assert self.fake_invalid_chronos_job_config._check_schedule_repeat_helper('R32') is True

    def test_check_schedule_repeat_helper_valid_infinite(self):
        assert self.fake_invalid_chronos_job_config._check_schedule_repeat_helper('R') is True

    def test_check_schedule_repeat_helper_invalid_empty(self):
        assert self.fake_invalid_chronos_job_config._check_schedule_repeat_helper('') is False

    def test_check_schedule_repeat_helper_invalid_no_r(self):
        assert self.fake_invalid_chronos_job_config._check_schedule_repeat_helper('32') is False

    def test_check_schedule_repeat_helper_invalid_float(self):
        assert self.fake_invalid_chronos_job_config._check_schedule_repeat_helper('R6.9') is False

    def test_check_schedule_repeat_helper_invalid_negative(self):
        assert self.fake_invalid_chronos_job_config._check_schedule_repeat_helper('R-8') is False

    def test_check_schedule_repeat_helper_invalid_other_text(self):
        assert self.fake_invalid_chronos_job_config._check_schedule_repeat_helper('BR72') is False

    def test_check_schedule_valid_complete(self):
        okay, msg = self.fake_chronos_job_config.check_schedule()
        assert okay is True
        assert msg == ''

    def test_check_schedule_valid_empty_start_time(self):
        fake_schedule = 'R10//PT2S'
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule': fake_schedule}, {})
        okay, msg = chronos_config.check_schedule()
        assert okay is True
        assert msg == ''

    def test_check_schedule_invalid_start_time_no_t_designator(self):
        fake_start_time = 'now'
        fake_schedule = 'R10/%s/PT2S' % fake_start_time
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule': fake_schedule}, {})
        fake_isodate_exception = 'ISO 8601 time designator \'T\' missing. Unable to parse datetime string \'now\''
        okay, msg = chronos_config.check_schedule()
        assert okay is False
        assert msg == ('The specified start time \'%s\' in schedule \'%s\' does not conform to the ISO 8601 format:\n%s'
                       % (fake_start_time, fake_schedule, fake_isodate_exception))

    def test_check_schedule_invalid_start_time_bad_date(self):
        fake_start_time = 'todayT19:20:30Z'
        fake_schedule = 'R10/%s/PT2S' % fake_start_time
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule': fake_schedule}, {})
        fake_isodate_exception = 'Unrecognised ISO 8601 date format: \'today\''
        okay, msg = chronos_config.check_schedule()
        assert okay is False
        assert msg == ('The specified start time \'%s\' in schedule \'%s\' does not conform to the ISO 8601 format:\n%s'
                       % (fake_start_time, fake_schedule, fake_isodate_exception))

    def test_check_schedule_invalid_start_time_bad_time(self):
        fake_start_time = '1994-02-18Tmorning'
        fake_schedule = 'R10/%s/PT2S' % fake_start_time
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule': fake_schedule}, {})
        fake_isodate_exception = 'Unrecognised ISO 8601 time format: \'morning\''
        okay, msg = chronos_config.check_schedule()
        assert okay is False
        assert msg == ('The specified start time \'%s\' in schedule \'%s\' does not conform to the ISO 8601 format:\n%s'
                       % (fake_start_time, fake_schedule, fake_isodate_exception))

    def test_check_schedule_invalid_empty_interval(self):
        fake_schedule = 'R10//'
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule': fake_schedule}, {})
        okay, msg = chronos_config.check_schedule()
        assert okay is False
        assert msg == ('The specified interval \'\' in schedule \'%s\' does not conform to the ISO 8601 format.'
                       % fake_schedule)

    def test_check_schedule_invalid_interval(self):
        fake_schedule = 'R10//Mondays'
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule': fake_schedule}, {})
        okay, msg = chronos_config.check_schedule()
        assert okay is False
        assert msg == ('The specified interval \'Mondays\' in schedule \'%s\' does not conform to the ISO 8601 format.'
                       % fake_schedule)

    def test_check_schedule_invalid_empty_repeat(self):
        fake_schedule = '//PT2S'
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule': fake_schedule}, {})
        okay, msg = chronos_config.check_schedule()
        assert okay is False
        assert msg == ('The specified repeat \'\' in schedule \'%s\' does not conform to the ISO 8601 format.'
                       % fake_schedule)

    def test_check_schedule_invalid_repeat(self):
        fake_schedule = 'forever//PT2S'
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule': fake_schedule}, {})
        okay, msg = chronos_config.check_schedule()
        assert okay is False
        assert msg == ('The specified repeat \'forever\' in schedule \'%s\' does not conform to the ISO 8601 format.'
                       % fake_schedule)

    def test_check_schedule_time_zone_valid(self):
        okay, msg = self.fake_chronos_job_config.check_schedule_time_zone()
        assert okay is True
        assert msg == ''

    def test_check_schedule_time_zone_valid_empty(self):
        chronos_config = chronos_tools.ChronosJobConfig('', {'schedule_time_zone': ''}, {})
        okay, msg = chronos_config.check_schedule_time_zone()
        assert okay is True
        assert msg == ''

    def test_check_schedule_time_zone_invalid(self):
        okay, msg = self.fake_invalid_chronos_job_config.check_schedule_time_zone()
        assert okay is True  # FIXME implement the validator
        assert msg == ''  # FIXME implement the validator
        # assert okay is False
        # assert msg == 'The specified time zone \'+0200\' does not conform to the tz database format.'

    def test_check_param_with_check(self):
        with contextlib.nested(
            mock.patch('chronos_tools.ChronosJobConfig.check_cpus', autospec=True),
        ) as (
            mock_check_cpus,
        ):
            mock_check_cpus.return_value = True, ''
            param = 'cpus'
            okay, msg = self.fake_chronos_job_config.check(param)
            assert mock_check_cpus.call_count == 1
            assert okay is True
            assert msg == ''

    def test_check_param_without_check(self):
        param = 'name'
        okay, msg = self.fake_chronos_job_config.check(param)
        assert okay is True
        assert msg == ''

    def test_check_unknown_param(self):
        param = 'boat'
        okay, msg = self.fake_chronos_job_config.check(param)
        assert okay is False
        assert msg == 'Your Chronos config specifies \'boat\', an unsupported parameter.'

    def test_set_missing_params_to_defaults(self):
        chronos_config_defaults = {
            # 'shell': 'true',  # we don't support this param, but it does have a default specified by the Chronos docs
            'epsilon': 'PT60S',
            'retries': 2,
            # 'async': False,  # we don't support this param, but it does have a default specified by the Chronos docs
            'cpus': 0.1,
            'mem': 128,
            'disk': 256,
            'disabled': False,
            # 'data_job': False, # we don't support this param, but it does have a default specified by the Chronos docs
        }
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', {}, {})
        completed_chronos_job_config = chronos_tools.set_missing_params_to_defaults(fake_chronos_job_config)
        for param in chronos_config_defaults:
            assert completed_chronos_job_config.get(param) == chronos_config_defaults[param]

    def test_set_missing_params_to_defaults_no_missing_params(self):
        chronos_config_dict = {
            'epsilon': 'PT5M',
            'retries': 5,
            'cpus': 7.2,
            'mem': 9001,
            'disk': 8,
            'disabled': True,
        }
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', chronos_config_dict, {})

        completed_chronos_job_config = chronos_tools.set_missing_params_to_defaults(fake_chronos_job_config)
        for param in chronos_config_dict:
            assert completed_chronos_job_config.get(param) == chronos_config_dict[param]

    def test_check_job_reqs(self):
        with contextlib.nested(
            mock.patch('chronos_tools._check_scheduled_job_reqs_helper', autospec=True),
        ) as (
            mock_check_scheduled_job_reqs_helper,
        ):
            mock_check_scheduled_job_reqs_helper.return_value = ''
            job_type = 'scheduled'
            okay, msgs = chronos_tools.check_job_reqs(self.fake_chronos_job_config, job_type)
            mock_check_scheduled_job_reqs_helper.assert_called_once_with(self.fake_chronos_job_config, job_type)
            assert okay is True
            assert len(msgs) == 0

    def test_check_job_reqs_scheduled_complete(self):
        okay, msgs = chronos_tools.check_job_reqs(self.fake_chronos_job_config, 'scheduled')
        assert okay is True
        assert len(msgs) == 0

    def test_check_job_reqs_scheduled_incomplete(self):
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', {}, {})
        okay, msgs = chronos_tools.check_job_reqs(fake_chronos_job_config, 'scheduled')
        assert okay is False
        assert 'Your Chronos config is missing \'name\', a required parameter for a \'scheduled job\'.' in msgs
        assert 'Your Chronos config is missing \'schedule\', a required parameter for a \'scheduled job\'.' in msgs

    def test_check_job_reqs_dependent_complete(self):
        fake_config_dict = {
            'name': 'test',
            'description': 'This is a test Chronos job.',
            'command': '/bin/sleep 40',
            'epsilon': 'PT30M',
            'retries': 5,
            'owner': 'test@test.com',
            'async': False,
            'cpus': 5.5,
            'mem': 1024.4,
            'disk': 2048.5,
            'disabled': 'true',
            'parents': ['jack', 'jill'],
        }
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', fake_config_dict, {})
        okay, msgs = chronos_tools.check_job_reqs(fake_chronos_job_config, 'dependent')
        assert okay is True
        assert len(msgs) == 0

    def test_check_job_reqs_dependent_incomplete(self):
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', {}, {})
        okay, msgs = chronos_tools.check_job_reqs(fake_chronos_job_config, 'dependent')
        assert okay is False
        assert 'Your Chronos config is missing \'name\', a required parameter for a \'dependent job\'.' in msgs
        assert 'Your Chronos config is missing \'parents\', a required parameter for a \'dependent job\'.' in msgs

    def test_check_job_reqs_docker_complete(self):
        fake_config_dict = {
            'name': 'test',
            'description': 'This is a test Chronos job.',
            'command': '/bin/sleep 40',
            'epsilon': 'PT30M',
            'retries': 5,
            'owner': 'test@test.com',
            'async': False,
            'cpus': 5.5,
            'mem': 1024.4,
            'disk': 2048.5,
            'disabled': 'true',
            'schedule': 'R/2015-03-25T19:36:35Z/PT5M',
            'schedule_time_zone': '',
            'container': {
                'type': 'DOCKER',
                'image': 'libmesos/ubuntu',
                'network': 'BRIDGE',
                'volumes': [{'containerPath': '/var/log/', 'hostPath': '/logs/', 'mode': 'RW'}]
            },
        }
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', fake_config_dict, {})
        okay, msgs = chronos_tools.check_job_reqs(fake_chronos_job_config, 'docker')
        assert okay is True
        assert len(msgs) == 0

    def test_check_job_reqs_docker_incomplete(self):
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', {}, {})
        okay, msgs = chronos_tools.check_job_reqs(fake_chronos_job_config, 'docker')
        assert okay is False
        assert 'Your Chronos config is missing \'name\', a required parameter for a \'docker job\'.' in msgs
        assert 'Your Chronos config is missing \'container\', a required parameter for a \'docker job\'.' in msgs

    def test_check_job_reqs_docker_invalid_neither_schedule_nor_parents(self):
        fake_config_dict = {
            'name': 'test',
            'description': 'This is a test Chronos job.',
            'command': '/bin/sleep 40',
            'epsilon': 'PT30M',
            'retries': 5,
            'owner': 'test@test.com',
            'async': False,
            'cpus': 5.5,
            'mem': 1024.4,
            'disk': 2048.5,
            'disabled': 'true',
            'container': {
                'type': 'DOCKER',
                'image': 'libmesos/ubuntu',
                'network': 'BRIDGE',
                'volumes': [{'containerPath': '/var/log/', 'hostPath': '/logs/', 'mode': 'RW'}]
            },
        }
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', fake_config_dict, {})
        okay, msgs = chronos_tools.check_job_reqs(fake_chronos_job_config, 'docker')
        assert okay is False
        assert ('Your Chronos config contains neither \'schedule\' nor \'parents\'. '
                'One is required for a \'docker job\'.') in msgs

    def test_check_job_reqs_docker_invalid_both_schedule_and_parents(self):
        fake_config_dict = {
            'name': 'test',
            'description': 'This is a test Chronos job.',
            'command': '/bin/sleep 40',
            'epsilon': 'PT30M',
            'retries': 5,
            'owner': 'test@test.com',
            'async': False,
            'cpus': 5.5,
            'mem': 1024.4,
            'disk': 2048.5,
            'disabled': 'true',
            'schedule': 'R/2015-03-25T19:36:35Z/PT5M',
            'schedule_time_zone': '',
            'parents': ['jack', 'jill'],
            'container': {
                'type': 'DOCKER',
                'image': 'libmesos/ubuntu',
                'network': 'BRIDGE',
                'volumes': [{'containerPath': '/var/log/', 'hostPath': '/logs/', 'mode': 'RW'}]
            },
        }
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', fake_config_dict, {})
        okay, msgs = chronos_tools.check_job_reqs(fake_chronos_job_config, 'docker')
        assert okay is False
        assert ('Your Chronos config contains both \'schedule\' and \'parents\'. '
                'Only one may be specified for a \'docker job\'.') in msgs

    def test_check_job_reqs_invalid_job_type(self):
        fake_job_type = 'boogaloo'
        fake_chronos_job_config = chronos_tools.ChronosJobConfig('', {}, {})
        okay, msgs = chronos_tools.check_job_reqs(fake_chronos_job_config, fake_job_type)
        assert okay is False
        assert msgs == '\'%s\' is not a supported job type. Aborting job requirements check.' % fake_job_type

    def test_format_chronos_job_dict(self):
        fake_service_name = 'test_service'
        fake_description = 'this service is just a test'
        fake_command = 'echo foo >> /tmp/test_service_log'
        fake_schedule = 'R10/2012-10-01T05:52:00Z/PT1M'
        fake_owner = 'bob@example.com'
        incomplete_config = chronos_tools.ChronosJobConfig(
            fake_service_name,
            {
                'name': fake_service_name,
                'description': fake_description,
                'command': fake_command,
                'schedule': fake_schedule,
                'owner': fake_owner,
            },
            {}
        )
        expected = {
            'name': fake_service_name,
            'description': fake_description,
            'command': fake_command,
            'schedule': fake_schedule,
            'epsilon': 'PT60S',
            'owner': fake_owner,
            'async': False,
            'cpus': 0.1,
            'mem': 128,
            'disk': 256,
            'retries': 2,
            'disabled': False,
        }
        actual = chronos_tools.format_chronos_job_dict(incomplete_config, 'scheduled')
        assert actual == expected

    def test_format_chronos_job_dict_invalid_param(self):
        fake_service_name = 'test_service'
        fake_description = 'this service is just a test'
        fake_command = 'echo foo >> /tmp/test_service_log'
        fake_schedule = 'R10/2012-10-01T05:52:00Z/PT1M'
        fake_owner = 'bob@example.com'
        incomplete_config = chronos_tools.ChronosJobConfig(
            fake_service_name,
            {
                'name': fake_service_name,
                'description': fake_description,
                'command': fake_command,
                'schedule': fake_schedule,
                'owner': fake_owner,
                'ship': 'Titanic',
            },
            {}
        )
        with raises(chronos_tools.InvalidChronosConfigError) as exc:
            chronos_tools.format_chronos_job_dict(incomplete_config, 'scheduled')
            assert exc.value == 'Your Chronos config specifies \'ship\', an unsupported parameter.'

    def test_format_chronos_job_dict_incomplete(self):
        fake_service_name = 'test_service'
        fake_description = 'this service is just a test'
        fake_command = 'echo foo >> /tmp/test_service_log'
        fake_schedule = 'R10/2012-10-01T05:52:00Z/PT1M'
        fake_owner = 'bob@example.com'
        incomplete_config = chronos_tools.ChronosJobConfig(
            fake_service_name,
            {
                'description': fake_description,
                'command': fake_command,
                'schedule': fake_schedule,
                'owner': fake_owner,
            },
            {}
        )
        with raises(chronos_tools.InvalidChronosConfigError) as exc:
            chronos_tools.format_chronos_job_dict(incomplete_config, 'scheduled')
            assert exc.value == 'Your Chronos config is missing \'name\', a required parameter for a \'scheduled job\'.'
