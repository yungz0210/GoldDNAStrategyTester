//+------------------------------------------------------------------+
//|                                             DataExtractor.mq5 |
//|                                     Strategy DNA Tester Tool |
//+------------------------------------------------------------------+
#property copyright "Strategy DNA Tester"
#property link      ""
#property version   "1.00"
#property script_show_inputs

//--- Inputs
input string   BaseFileName = "live_results";    // Output CSV Base Name
input int      ATR_Period = 14;                  // ATR Period
input int      StdDev_Period = 20;               // StdDev Period

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
  {
   Print("StrategyDNA: Live Extraction started...");

   // Versioning: Append YYYYMMDD_HHMMSS to the filename
   string timestamp = TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS);
   StringReplace(timestamp, ".", "");
   StringReplace(timestamp, ":", "");
   StringReplace(timestamp, " ", "_");
   string FinalFileName = BaseFileName + "_" + timestamp + ".csv";

   // Open or create the CSV file in MQL5/Files/
   int file_handle = FileOpen(FinalFileName, FILE_CSV|FILE_WRITE|FILE_ANSI, ",");
   if(file_handle == INVALID_HANDLE)
     {
      Print("StrategyDNA Error: Could not open file: ", FinalFileName, " | Error Code: ", GetLastError());
      return;
     }

   // Write header row
   string header = "Ticket,Symbol,Type,EntryTime,ExitTime,DurationSec,EntryPrice,ExitPrice,Volume,MAE,MFE,Commission,Swap,PnL,ATR,StdDev,EntryHour";
   FileWrite(file_handle, header);

   // Request trade history
   if(!HistorySelect(0, TimeCurrent()))
     {
      Print("Error requesting history: ", GetLastError());
      FileClose(file_handle);
      return;
     }

   int total_deals = HistoryDealsTotal();
   int atr_handle = iATR(_Symbol, PERIOD_CURRENT, ATR_Period);
   int stddev_handle = iStdDev(_Symbol, PERIOD_CURRENT, StdDev_Period, 0, MODE_SMA, PRICE_CLOSE);

   if(atr_handle == INVALID_HANDLE || stddev_handle == INVALID_HANDLE)
     {
      Print("Error creating indicator handles.");
      FileClose(file_handle);
      return;
     }

   // Pass 1: Gather all unique Position IDs from deals
   long pos_ids[];
   int pos_count = 0;

   for(int i = 0; i < total_deals; i++)
     {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0) continue;

      long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
      if(deal_entry != DEAL_ENTRY_OUT) continue; // We only care about positions that have been closed

      long pos_id = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);

      // Check if already in array
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

      // Select the history of the position
      // Note: This overrides the global history list selected by HistorySelect(0, TimeCurrent())
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

      // We loop through deals in this specific position
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
            if(entry_deal_ticket == 0) // Take the first entry
              {
               entry_deal_ticket = d_ticket;
               entry_time = (datetime)HistoryDealGetInteger(d_ticket, DEAL_TIME);
               entry_price = HistoryDealGetDouble(d_ticket, DEAL_PRICE);
               total_volume = deal_vol;
              }
           }
         else if(d_entry == DEAL_ENTRY_OUT || d_entry == DEAL_ENTRY_INOUT)
           {
            // Update the exit details (in case of partial closes, this takes the last one)
            exit_deal_ticket = d_ticket;
            exit_time = (datetime)HistoryDealGetInteger(d_ticket, DEAL_TIME);
            exit_price = HistoryDealGetDouble(d_ticket, DEAL_PRICE);
           }
        }

      if(entry_deal_ticket == 0 || exit_deal_ticket == 0) continue;

      // Calculate Net PnL to be accurate for Integrity Score
      double net_pnl = base_pnl + total_commission + total_swap;

      long deal_type = HistoryDealGetInteger(exit_deal_ticket, DEAL_TYPE);
      string type_str = (deal_type == DEAL_TYPE_BUY) ? "BUY_TO_COVER" : "SELL_TO_COVER";

      double mae = 0.0;
      double mfe = 0.0;

      // Calculate MAE and MFE using historical rates between entry and exit
      double high_rates[], low_rates[];
      int copied_high = CopyHigh(_Symbol, PERIOD_M1, entry_time, exit_time, high_rates);
      int copied_low = CopyLow(_Symbol, PERIOD_M1, entry_time, exit_time, low_rates);

      if(copied_high > 0 && copied_low > 0)
        {
         double highest_price = high_rates[ArrayMaximum(high_rates)];
         double lowest_price = low_rates[ArrayMinimum(low_rates)];

         // If closing deal was BUY (we were short)
         if(deal_type == DEAL_TYPE_BUY)
           {
            // For a short, MFE is the lowest price reached (most profit), MAE is the highest price (most loss)
            mfe = entry_price - lowest_price;
            mae = highest_price - entry_price;
           }
         // If closing deal was SELL (we were long)
         else
           {
            // For a long, MFE is the highest price reached, MAE is the lowest price
            mfe = highest_price - entry_price;
            mae = entry_price - lowest_price;
           }

         // MAE/MFE are strictly non-negative by definition. If it didn't go against/for us, it's 0.
         mfe = MathMax(0.0, mfe);
         mae = MathMax(0.0, mae);
        }

      long duration_sec = exit_time - entry_time;

      // Indicator Context at Entry Time
      double atr_array[1];
      double stddev_array[1];

      int shift = iBarShift(_Symbol, PERIOD_CURRENT, entry_time);
      double atr_val = 0.0;
      double stddev_val = 0.0;

      if(shift >= 0)
        {
         if(CopyBuffer(atr_handle, 0, shift, 1, atr_array) > 0) atr_val = atr_array[0];
         if(CopyBuffer(stddev_handle, 0, shift, 1, stddev_array) > 0) stddev_val = stddev_array[0];
        }

      MqlDateTime time_struct;
      TimeToStruct(entry_time, time_struct);
      int entry_hour = time_struct.hour;

      // Formatting CSV Row
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
   IndicatorRelease(atr_handle);
   IndicatorRelease(stddev_handle);
   Print("StrategyDNA: SUCCESS! Live data extraction complete.");
   Print("StrategyDNA: You can find your file at: MQL5/Files/", FinalFileName);
   Print("StrategyDNA: (In MetaTrader 5, click File -> Open Data Folder -> MQL5 -> Files)");
  }
//+------------------------------------------------------------------+