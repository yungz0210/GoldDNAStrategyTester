//+------------------------------------------------------------------+
//|                                                StrategyDNA.mqh   |
//|                                     Strategy DNA Tester Tool     |
//+------------------------------------------------------------------+
#property copyright "Strategy DNA Tester"
#property link      ""
#property version   "1.02"

//+------------------------------------------------------------------+
//| Helper Function: Calculate ATR manually at a specific time       |
//+------------------------------------------------------------------+
double CalculateATR(string symbol, ENUM_TIMEFRAMES timeframe, datetime entry_time, int period)
  {
   // Find the shift for the given entry time
   int shift = iBarShift(symbol, timeframe, entry_time);
   if(shift < 0) return 0.0;

   // We need to calculate True Range for 'period' bars prior to the entry shift
   // True Range requires the High, Low, and Previous Close.
   // So we need 'period' + 1 bars.
   double high[], low[], close[];
   int copied_h = CopyHigh(symbol, timeframe, shift, period + 1, high);
   int copied_l = CopyLow(symbol, timeframe, shift, period + 1, low);
   int copied_c = CopyClose(symbol, timeframe, shift, period + 1, close);

   if(copied_h < period + 1 || copied_l < period + 1 || copied_c < period + 1)
      return 0.0;

   double sum_tr = 0.0;

   // Loop through the 'period' bars (skipping index 0 which is just the "previous close" of the oldest bar)
   // Arrays from Copy... are oldest first (index 0) to newest last (index 'period')
   for(int i = 1; i <= period; i++)
     {
      double h = high[i];
      double l = low[i];
      double prev_c = close[i-1];

      double tr = MathMax(h - l, MathMax(MathAbs(h - prev_c), MathAbs(l - prev_c)));
      sum_tr += tr;
     }

   return sum_tr / period;
  }

//+------------------------------------------------------------------+
//| Helper Function: Calculate StdDev manually at a specific time    |
//+------------------------------------------------------------------+
double CalculateStdDev(string symbol, ENUM_TIMEFRAMES timeframe, datetime entry_time, int period)
  {
   // Find the shift for the given entry time
   int shift = iBarShift(symbol, timeframe, entry_time);
   if(shift < 0) return 0.0;

   double close[];
   int copied_c = CopyClose(symbol, timeframe, shift, period, close);

   if(copied_c < period)
      return 0.0;

   double sum = 0.0;
   for(int i = 0; i < period; i++) sum += close[i];

   double sma = sum / period;

   double sum_sq_diff = 0.0;
   for(int i = 0; i < period; i++)
     {
      double diff = close[i] - sma;
      sum_sq_diff += diff * diff;
     }

   return MathSqrt(sum_sq_diff / period);
  }

//+------------------------------------------------------------------+
//| Call this function inside your Expert Advisor's OnDeinit()       |
//+------------------------------------------------------------------+
void ExportStrategyDNA(string BaseFileName="backtest", int ATR_Period=14, int StdDev_Period=20)
  {
   Print("StrategyDNA: Initialization started in OnDeinit(). Generating report...");

   // Versioning: Append YYYYMMDD_HHMMSS to the filename
   string timestamp = TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS);
   StringReplace(timestamp, ".", "");
   StringReplace(timestamp, ":", "");
   StringReplace(timestamp, " ", "_");
   string FinalFileName = BaseFileName + "_" + timestamp + ".csv";

   // We USE FILE_COMMON here to break out of the hidden Tester/Agent-XXXX/MQL5/Files/ directory
   // It will save directly to the globally accessible Terminal/Common/Files/ folder
   int file_handle = FileOpen(FinalFileName, FILE_CSV|FILE_WRITE|FILE_ANSI|FILE_COMMON, ",");
   if(file_handle == INVALID_HANDLE)
     {
      Print("StrategyDNA Error: Could not open file: ", FinalFileName, " | Error Code: ", GetLastError());
      return;
     }

   string header = "Ticket,Symbol,Type,EntryTime,ExitTime,DurationSec,EntryPrice,ExitPrice,Volume,MAE,MFE,Commission,Swap,PnL,ATR,StdDev,EntryHour";
   FileWrite(file_handle, header);

   if(!HistorySelect(0, TimeCurrent()))
     {
      Print("StrategyDNA Error: Could not request history: ", GetLastError());
      FileClose(file_handle);
      return;
     }

   Print("StrategyDNA: Analyzing history deals...");

   int total_deals = HistoryDealsTotal();

   // Pass 1: Gather all unique Position IDs from deals
   long pos_ids[];
   int pos_count = 0;

   for(int i = 0; i < total_deals; i++)
     {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0) continue;

      long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
      if(deal_entry != DEAL_ENTRY_OUT) continue;

      long pos_id = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);

      bool exists = false;
      for(int k = 0; k < pos_count; k++)
        {
         if(pos_ids[k] == pos_id)
           {
            exists = true;
            break;
           }
        }

      if(!exists)
        {
         ArrayResize(pos_ids, pos_count + 1);
         pos_ids[pos_count] = pos_id;
         pos_count++;
        }
     }

   // Pass 2: Process each Position ID
   for(int i = 0; i < pos_count; i++)
     {
      long pos_id = pos_ids[i];

      if(!HistorySelectByPosition(pos_id)) continue;

      double total_commission = 0;
      double total_swap = 0;
      double base_pnl = 0;
      double total_volume = 0;

      ulong entry_deal_ticket = 0;
      ulong exit_deal_ticket = 0;

      datetime entry_time = 0;
      datetime exit_time = 0;

      double entry_price = 0;
      double exit_price = 0;

      int deals_in_pos = HistoryDealsTotal();

      for(int j = 0; j < deals_in_pos; j++)
        {
         ulong d_ticket = HistoryDealGetTicket(j);

         double deal_com = HistoryDealGetDouble(d_ticket, DEAL_COMMISSION);
         double deal_swp = HistoryDealGetDouble(d_ticket, DEAL_SWAP);
         double deal_prof = HistoryDealGetDouble(d_ticket, DEAL_PROFIT);
         double deal_vol = HistoryDealGetDouble(d_ticket, DEAL_VOLUME);

         total_commission += deal_com;
         total_swap += deal_swp;
         base_pnl += deal_prof;

         long d_entry = HistoryDealGetInteger(d_ticket, DEAL_ENTRY);

         if(d_entry == DEAL_ENTRY_IN)
           {
            if(entry_deal_ticket == 0)
              {
               entry_deal_ticket = d_ticket;
               entry_time = (datetime)HistoryDealGetInteger(d_ticket, DEAL_TIME);
               entry_price = HistoryDealGetDouble(d_ticket, DEAL_PRICE);
               total_volume = deal_vol;
              }
           }
         else if(d_entry == DEAL_ENTRY_OUT || d_entry == DEAL_ENTRY_INOUT)
           {
            exit_deal_ticket = d_ticket;
            exit_time = (datetime)HistoryDealGetInteger(d_ticket, DEAL_TIME);
            exit_price = HistoryDealGetDouble(d_ticket, DEAL_PRICE);
           }
        }

      if(entry_deal_ticket == 0 || exit_deal_ticket == 0) continue;

      double net_pnl = base_pnl + total_commission + total_swap;

      long deal_type = HistoryDealGetInteger(exit_deal_ticket, DEAL_TYPE);
      string type_str = (deal_type == DEAL_TYPE_BUY) ? "BUY_TO_COVER" : "SELL_TO_COVER";

      double mae = 0.0;
      double mfe = 0.0;

      double high_rates[], low_rates[];
      int copied_high = CopyHigh(_Symbol, PERIOD_M1, entry_time, exit_time, high_rates);
      int copied_low = CopyLow(_Symbol, PERIOD_M1, entry_time, exit_time, low_rates);

      if(copied_high > 0 && copied_low > 0)
        {
         double highest_price = high_rates[ArrayMaximum(high_rates)];
         double lowest_price = low_rates[ArrayMinimum(low_rates)];

         if(deal_type == DEAL_TYPE_BUY)
           {
            mfe = entry_price - lowest_price;
            mae = highest_price - entry_price;
           }
         else
           {
            mfe = highest_price - entry_price;
            mae = entry_price - lowest_price;
           }

         mfe = MathMax(0.0, mfe);
         mae = MathMax(0.0, mae);
        }

      long duration_sec = exit_time - entry_time;

      // Calculate Indicators Manually (OnDeinit Safe)
      double atr_val = CalculateATR(_Symbol, PERIOD_CURRENT, entry_time, ATR_Period);
      double stddev_val = CalculateStdDev(_Symbol, PERIOD_CURRENT, entry_time, StdDev_Period);

      MqlDateTime time_struct;
      TimeToStruct(entry_time, time_struct);
      int entry_hour = time_struct.hour;

      string row = StringFormat("%I64u,%s,%s,%s,%s,%d,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%d",
                                pos_id,
                                _Symbol,
                                type_str,
                                TimeToString(entry_time, TIME_DATE|TIME_MINUTES|TIME_SECONDS),
                                TimeToString(exit_time, TIME_DATE|TIME_MINUTES|TIME_SECONDS),
                                duration_sec,
                                entry_price,
                                exit_price,
                                total_volume,
                                mae,
                                mfe,
                                total_commission,
                                total_swap,
                                net_pnl,
                                atr_val,
                                stddev_val,
                                entry_hour);

      FileWrite(file_handle, row);
     }

   FileClose(file_handle);
   Print("StrategyDNA: SUCCESS! Backtest data extraction complete.");
   Print("StrategyDNA: You can find your file at: Terminal/Common/Files/", FinalFileName);
   Print("StrategyDNA: (In MT5, click File -> Open Data Folder -> Up one level to MetaQuotes -> Terminal -> Common -> Files)");
  }
//+------------------------------------------------------------------+