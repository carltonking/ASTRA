import React from 'react';
import { render, screen } from '@testing-library/react';

jest.mock('../../../hooks/useAlpaca', () => () => ({
  configured: false,
  account: null,
  positions: [],
  orders: [],
  portfolioHistory: null,
  lastUpdated: null,
  fetchAccount: jest.fn(),
  fetchPositions: jest.fn(),
  fetchOrders: jest.fn(),
  fetchPortfolioHistory: jest.fn(),
  cancelOrder: jest.fn(),
}));

describe('PaperTrading', () => {
  it('shows broker config message when not configured', () => {
    const PaperTrading = require('../PaperTrading').default;
    const { container } = render(<PaperTrading session={null} isActive={false} />);
    expect(container.textContent).toContain('broker');
  });
});
