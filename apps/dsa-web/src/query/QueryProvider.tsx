// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { createAppQueryClient } from './createAppQueryClient';

type QueryProviderProps = {
  children: React.ReactNode;
  client?: QueryClient;
};

export const QueryProvider: React.FC<QueryProviderProps> = ({ children, client }) => {
  const [ownedClient] = useState(() => client ?? createAppQueryClient());
  return (
    <QueryClientProvider client={client ?? ownedClient}>
      {children}
    </QueryClientProvider>
  );
};

export default QueryProvider;
