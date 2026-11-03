import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import api from '../api';
import VenueRecommenderEnhanced from './VenueRecommenderEnhanced';
jest.mock('../api', () => ({ post: jest.fn() }));
beforeEach(() => jest.clearAllMocks());
test('sends private job reference and strict filter preferences', async () => {
  api.post.mockResolvedValue({ data: { eligible_venues: 1, matching: { method: 'tfidf' }, venues: [{ name: 'Journal X', match_score: 42, reason: 'Subject metadata', language: 'ENG' }] } });
  render(<VenueRecommenderEnhanced jobId="owned-job" />);
  fireEvent.click(screen.getByLabelText('Medline only'));
  fireEvent.click(screen.getByRole('button', { name: 'Get recommendations' }));
  expect(await screen.findByText('Journal X')).toBeInTheDocument();
  const body = api.post.mock.calls[0][1];
  expect(body.job_id).toBe('owned-job');
  expect(body.medline_only).toBe(true);
  expect(body.exclude_discontinued).toBe(true);
  expect(body.paper_text).toBeUndefined();
});

test('directory sends fee and currency filters without a manuscript', async () => {
  api.post.mockResolvedValue({ data: { venues: [], total: 0, page: 1, pages: 1 } });
  render(<VenueRecommenderEnhanced />);
  fireEvent.click(screen.getByRole('button', { name: 'Browse public directory' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Apply filters' })).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Publication fees'), { target: { value: 'paid' } });
  fireEvent.change(screen.getByLabelText('Maximum APC'), { target: { value: '200' } });
  fireEvent.change(screen.getByLabelText('Currency'), { target: { value: 'INR' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));
  await waitFor(() => expect(api.post).toHaveBeenLastCalledWith('/api/venues', expect.objectContaining({ fee_status: 'paid', max_apc: 200, currency: 'INR', page: 1 }), expect.any(Object)));
  expect(api.post.mock.calls.at(-1)[1].job_id).toBeUndefined();
});

test('unknown costs are not labeled free and reported prices retain currency', async () => {
  api.post.mockResolvedValue({ data: { venues: [
    { name: 'Unknown Journal' },
    { name: 'Paid Journal', fees: { status: 'paid', apc_prices: [{ amount: 750, currency: 'EUR' }] } },
    { name: 'Free Journal', fees: { status: 'free', apc_prices: [] } }
  ], total: 3, page: 1, pages: 1 } });
  render(<VenueRecommenderEnhanced />);
  fireEvent.click(screen.getByRole('button', { name: 'Browse public directory' }));
  expect(await screen.findByText('EUR 750')).toBeInTheDocument();
  expect(screen.getByText('Fee not verified', { selector: 'strong' })).toBeInTheDocument();
  expect(screen.getAllByText('Free to publish', { selector: 'strong' })).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: 'Cards' }));
  expect(screen.getByRole('button', { name: 'Cards' })).toHaveAttribute('aria-pressed', 'true');
});
