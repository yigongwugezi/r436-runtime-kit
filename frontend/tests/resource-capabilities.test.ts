import assert from 'node:assert/strict';
import test from 'node:test';
import { resourceCapability, resourceErrorMessage } from '../src/utils/resourceCapabilities.ts';

test('provider capabilities disable only resources that need that provider', () => {
  const status = { llm: 'available', ppt: 'not_configured', video: 'not_configured', image: 'not_configured', mindmap: 'not_configured' } as const;
  assert.equal(resourceCapability('lecture', status).enabled, true);
  assert.equal(resourceCapability('ppt', status).enabled, false);
  assert.match(resourceCapability('ppt', status).reason || '', /未配置/);
  assert.equal(resourceCapability('video', status).enabled, false);
  assert.equal(resourceCapability('image', status).enabled, false);
  assert.equal(resourceCapability('mindmap', status).enabled, true);
  assert.equal(resourceCapability('mindmap', status).fallbackAvailable, true);
});

test('dependency, unsupported, and failed capability reads remain safe', () => {
  assert.match(resourceCapability('manim', { manim: 'dependency_missing' }).reason || '', /必要依赖/);
  assert.match(resourceCapability('ppt', { ppt: 'unsupported' }).reason || '', /不支持/);
  assert.equal(resourceCapability('lecture').enabled, false);
  assert.equal(resourceCapability('mindmap').enabled, true);
});

test('runtime errors are safe and only retryable errors invite retry', () => {
  assert.equal(resourceErrorMessage('network_unavailable').retryable, true);
  assert.equal(resourceErrorMessage('provider_timeout').retryable, true);
  assert.equal(resourceErrorMessage('provider_rate_limited').retryable, true);
  assert.equal(resourceErrorMessage('provider_invalid_response').retryable, true);
  assert.equal(resourceErrorMessage('generation_failed').retryable, true);
  const auth = resourceErrorMessage('provider_auth_failed');
  assert.equal(auth.retryable, false);
  assert.doesNotMatch(auth.message, /key|token|url|环境变量/i);
});
