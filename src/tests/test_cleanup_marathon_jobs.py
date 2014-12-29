#!/usr/bin/env python

import cleanup_marathon_jobs
import mock
import contextlib


class TestCleanupMarathonJobs:

    cleanup_marathon_jobs.log = mock.Mock()
    fake_docker_registry = 'http://del.icio.us/'
    fake_marathon_config = {
        'cluster': 'mess',
        'url': 'http://mess_url',
        'user': 'namnin',
        'pass': 'pass_nememim',
        'docker_registry': fake_docker_registry,
        'docker_volumes': [
            {
                'hostPath': '/var/data/a',
                'containerPath': '/etc/a',
                'mode': 'RO',
            },
            {
                'hostPath': '/var/data/b',
                'containerPath': '/etc/b',
                'mode': 'RW',
            },
        ],
    }
    fake_marathon_client = mock.Mock()

    def test_main(self):
        soa_dir = 'paasta_maaaachine'
        fake_args = mock.Mock(verbose=False, soa_dir=soa_dir)
        with contextlib.nested(
            mock.patch('cleanup_marathon_jobs.parse_args', return_value=fake_args),
            mock.patch('cleanup_marathon_jobs.cleanup_apps')
        ) as (
            args_patch,
            cleanup_patch
        ):
            cleanup_marathon_jobs.main()
            args_patch.assert_called_once_with()
            cleanup_patch.assert_called_once_with(soa_dir)

    def test_get_valid_app_list(self):
        soa_dir = 'never_a_dir'
        fake_app_list = [('fake-app', 'one'), ('really-fake', 'two')]
        fake_config_one = {'docker_image': 'srv:9.1'}
        fake_config_two = {'docker_image': 'tree:1.0'}
        fake_configs = [fake_config_two, fake_config_one]
        fake_full_configs = ['not_actually', 'a_dictionary']
        fake_code_sha = 'abc123'
        expected = ['fake-app.one.%s.%s' % (fake_code_sha, str(hash('a_dictionary'))),
                    'really-fake.two.%s.%s' % (fake_code_sha, str(hash('not_actually')))]
        fake_tag1 = "%s.%s" % (fake_code_sha, str(hash('a_dictionary')))
        fake_tag2 = "%s.%s" % (fake_code_sha, str(hash('not_actually')))

        def compose_helper(name, instance, hashtag=None):
            if hashtag:
                return '%s.%s.%s' % (name, instance, hashtag)
            else:
                return '%s.%s' % (name, instance)

        with contextlib.nested(
            mock.patch('paasta_tools.marathon_tools.get_marathon_services_for_cluster',
                       return_value=fake_app_list),
            mock.patch('paasta_tools.marathon_tools.compose_job_id',
                       side_effect=compose_helper),
            mock.patch('paasta_tools.marathon_tools.read_service_config',
                       side_effect=lambda a, b, **kwargs: fake_configs.pop()),
            mock.patch('paasta_tools.marathon_tools.get_docker_url',
                       side_effect=lambda a, b, **kwargs: '%s/%s' % (a, b)),
            mock.patch('paasta_tools.marathon_tools.create_complete_config',
                       side_effect=lambda a, b, c, d: fake_full_configs.pop()),
            mock.patch('paasta_tools.marathon_tools.get_config_hash',
                       side_effect=lambda a: hash(str(a))),
            mock.patch('paasta_tools.marathon_tools.get_code_sha_from_dockerurl',
                       return_value=fake_code_sha),
        ) as (
            get_srvs_patch,
            compose_patch,
            read_config_patch,
            docker_url_patch,
            complete_config_patch,
            hash_patch,
            code_sha_patch
        ):
            actual = cleanup_marathon_jobs.get_valid_app_list(self.fake_marathon_config, soa_dir)
            assert expected == actual
            get_srvs_patch.assert_called_once_with(soa_dir=soa_dir)
            compose_patch.assert_any_call('fake-app', 'one')
            compose_patch.assert_any_call('fake-app', 'one', fake_tag1)
            compose_patch.assert_any_call('really-fake', 'two')
            compose_patch.assert_any_call('really-fake', 'two', fake_tag2)
            assert compose_patch.call_count == 4
            read_config_patch.assert_any_call('fake-app', 'one', soa_dir=soa_dir)
            read_config_patch.assert_any_call('really-fake', 'two', soa_dir=soa_dir)
            assert read_config_patch.call_count == 2
            docker_url_patch.assert_any_call(self.fake_docker_registry,
                                             'tree:1.0', verify=False)
            docker_url_patch.assert_any_call(self.fake_docker_registry,
                                             'srv:9.1', verify=False)
            assert docker_url_patch.call_count == 2
            complete_config_patch.assert_any_call('fake-app.one',
                                                  '%s/%s' % (self.fake_docker_registry, 'srv:9.1'),
                                                  self.fake_marathon_config['docker_volumes'],
                                                  fake_config_one)
            complete_config_patch.assert_any_call('really-fake.two',
                                                  '%s/%s' % (self.fake_docker_registry, 'tree:1.0'),
                                                  self.fake_marathon_config['docker_volumes'],
                                                  fake_config_two)
            assert complete_config_patch.call_count == 2
            hash_patch.assert_any_call('not_actually')
            hash_patch.assert_any_call('a_dictionary')
            assert hash_patch.call_count == 2

    def test_cleanup_apps(self):
        from contextlib import contextmanager
        soa_dir = 'not_really_a_dir'
        fake_valid_apps = ['present.away.gone', 'on-app.off.stop']
        fake_app_ids = [mock.Mock(id='present.away.gone'), mock.Mock(id='on-app.off.stop'),
                        mock.Mock(id='not-here.oh.no')]
        self.fake_marathon_client.list_apps = mock.Mock(return_value=fake_app_ids)
        with contextlib.nested(
            mock.patch('cleanup_marathon_jobs.get_valid_app_list', return_value=fake_valid_apps),
            mock.patch('paasta_tools.marathon_tools.get_config',
                       return_value=self.fake_marathon_config),
            mock.patch('paasta_tools.marathon_tools.remove_tag_from_job_id',
                       return_value='a_location'),
            mock.patch('paasta_tools.bounce_lib.bounce_lock_zookeeper', spec=contextmanager),
            mock.patch('paasta_tools.marathon_tools.get_marathon_client', return_value=self.fake_marathon_client),
            mock.patch('paasta_tools.bounce_lib.delete_marathon_app')
        ) as (
            get_valid_patch,
            config_patch,
            remove_patch,
            bounce_patch,
            client_patch,
            delete_patch
        ):
            cleanup_marathon_jobs.cleanup_apps(soa_dir)
            config_patch.assert_called_once_with()
            get_valid_patch.assert_called_once_with(self.fake_marathon_config, soa_dir)
            client_patch.assert_called_once_with(self.fake_marathon_config['url'],
                                                 self.fake_marathon_config['user'],
                                                 self.fake_marathon_config['pass'])
            remove_patch.assert_called_once_with('not-here.oh.no')
            bounce_patch.assert_called_once_with('a_location')
            delete_patch.assert_called_once_with('not-here.oh.no', self.fake_marathon_client)

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4