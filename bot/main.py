async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file upload with progress feedback"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    if not context.user_data.get('uploading'):
        return
    
    document = update.message.document
    filename = document.file_name
    
    if filename.endswith(('.txt', '.csv', '.dat', '.log', '.tsv')):
        await update.message.reply_text("⏳ Downloading file...")
        print(f"📁 Downloading file: {filename}")
        
        try:
            os.makedirs("uploads", exist_ok=True)
            file_path = f"uploads/{filename}"
            file = await context.bot.get_file(document.file_id)
            await file.download_to_drive(file_path)
            print(f"✅ File downloaded to: {file_path}")
            
            if not os.path.exists(file_path):
                await update.message.reply_text(f"❌ File not found at: {file_path}")
                context.user_data['uploading'] = False
                return
            
            file_size = os.path.getsize(file_path)
            print(f"📊 File size: {file_size} bytes")
            
            session = SessionLocal()
            try:
                cards = []
                success_count = 0
                failed_count = 0
                total_lines = 0
                
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        total_lines += 1
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        delimiters = [',', '|', '\t', ' ']
                        delimiter = max(delimiters, key=lambda d: line.count(d))
                        parts = [p.strip() for p in line.split(delimiter)]
                        
                        print(f"📝 Line {line_num}: {len(parts)} parts, delimiter: '{delimiter}'")
                        
                        if len(parts) >= 4:
                            try:
                                card_number = parts[0]
                                expiry_month = parts[1]
                                expiry_year = parts[2]
                                cvv = parts[3]
                                
                                if not card_number.isdigit() or len(card_number) < 13 or len(card_number) > 19:
                                    failed_count += 1
                                    print(f"⚠️ Line {line_num}: Invalid card number")
                                    continue
                                
                                expiry = f"{expiry_month}/{expiry_year}"
                                bin_number = card_number[:6]
                                
                                # Default values
                                country = parts[4] if len(parts) > 4 and len(parts[4]) == 2 else 'US'
                                billing = parts[5] in ['1', 'True', 'yes', 'true'] if len(parts) > 5 else False
                                price = float(parts[6]) if len(parts) > 6 and parts[6].replace('.', '').isdigit() else DEFAULT_NAKED_PRICE
                                
                                card = Card(
                                    bin=bin_number,
                                    number=card_number,
                                    expiry=expiry,
                                    cvv=cvv,
                                    country=country,
                                    billing=billing,
                                    price=price,
                                    is_sold=False
                                )
                                cards.append(card)
                                success_count += 1
                            except (ValueError, IndexError) as e:
                                failed_count += 1
                                print(f"❌ Line {line_num} parse error: {e}")
                        else:
                            failed_count += 1
                            print(f"⚠️ Line {line_num}: Only {len(parts)} parts (need 4+)")
                
                print(f"✅ Cards to insert: {success_count}")
                print(f"❌ Failed lines: {failed_count}")
                
                if success_count > 0:
                    session.bulk_insert_mappings(Card, [c.__dict__ for c in cards])
                    session.commit()
                
                total = session.query(Card).count()
                available = session.query(Card).filter(Card.is_sold == False).count()
                
                await update.message.reply_text(
                    f"✅ **UPLOAD COMPLETE!**\n\n"
                    f"{'━'*40}\n"
                    f"📊 Cards Uploaded: {success_count}\n"
                    f"❌ Failed Lines: {failed_count}\n"
                    f"📈 Total Cards: {total}\n"
                    f"📉 Available: {available}\n"
                    f"{'━'*40}\n\n"
                    f"💰 Default Price: ${DEFAULT_NAKED_PRICE} USDT\n"
                    f"📁 File: `{filename}`\n"
                    f"📊 File Size: {file_size} bytes",
                    parse_mode="Markdown"
                )
                context.user_data['uploading'] = False
            
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                print(f"❌ Upload error: {error_msg}")
                if len(error_msg) > 3900:
                    error_msg = error_msg[:3900] + "...\n[Truncated]"
                await update.message.reply_text(f"❌ **Upload Error:**\n\n{error_msg}")
                context.user_data['uploading'] = False
                session.rollback()
            finally:
                session.close()
        
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            print(f"❌ Download error: {error_msg}")
            if len(error_msg) > 3900:
                error_msg = error_msg[:3900] + "...\n[Truncated]"
            await update.message.reply_text(f"❌ **Download Error:**\n\n{error_msg}")
            context.user_data['uploading'] = False
    else:
        await update.message.reply_text("❌ Unsupported file format. Use .txt or .csv")

# ============================================================================
# ⚙️ MAIN BOT SETUP
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    logging.error(f"Exception while handling an update: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An error occurred. Please try again.\n\n"
                "If the problem persists, contact support."
            )
        except:
            pass

def main():
    """Main bot initialization"""
    print("✅ Starting bot...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("topup", topup))
    application.add_handler(CommandHandler("catalog", catalog))
    application.add_handler(CommandHandler("bin", bin_lookup))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("upload", admin_upload))
    application.add_handler(CommandHandler("edit_price", admin_edit_price))
    application.add_handler(CommandHandler("add_price", admin_add_price))
    application.add_handler(CommandHandler("export", admin_export))
    
    # Regex Handlers
    application.add_handler(MessageHandler(filters.Regex('^/bin '), handle_bin_search))
    application.add_handler(MessageHandler(filters.Regex('^/edit_price '), handle_edit_price))
    application.add_handler(MessageHandler(filters.Regex('^/add_price '), handle_add_price))
    
    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(menu_navigator, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(copy_usdt, pattern="^copy_usdt$"))
    application.add_handler(CallbackQueryHandler(confirm_deposit, pattern="^confirm_deposit$"))
    application.add_handler(CallbackQueryHandler(catalog_callback, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(buy_card_callback, pattern="^buy_card_"))
    application.add_handler(CallbackQueryHandler(confirm_buy_callback, pattern="^confirm_buy_"))
    application.add_handler(CallbackQueryHandler(country_callback, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(order_bin_callback, pattern="^order_bin_"))
    application.add_handler(CallbackQueryHandler(handle_quantity_selection, pattern="^qty_"))
    application.add_handler(CallbackQueryHandler(view_history, pattern="^view_history$"))
    application.add_handler(CallbackQueryHandler(admin_export, pattern="^admin_export$"))
    application.add_handler(CallbackQueryHandler(admin_upload, pattern="^admin_upload$"))
    
    # Message Handlers
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin_order))
    
    # Error Handler
    application.add_error_handler(error_handler)
    
    print("✅ Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
        print("✅ Bot started successfully!")
    except Exception as e:
        import traceback
        print(f"❌ Bot crashed: {e}")
        traceback.print_exc()
        sys.exit(1)
async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file upload with progress feedback"""
    user = await get_or_create_user(update.effective_user.id)
    if not user.is_admin:
        await update.message.reply_text("🔒 Admin command only!")
        return
    if not context.user_data.get('uploading'):
        return
    
    document = update.message.document
    filename = document.file_name
    
    if filename.endswith(('.txt', '.csv', '.dat', '.log', '.tsv')):
        await update.message.reply_text("⏳ Downloading file...")
        print(f"📁 Downloading file: {filename}")
        
        try:
            os.makedirs("uploads", exist_ok=True)
            file_path = f"uploads/{filename}"
            file = await context.bot.get_file(document.file_id)
            await file.download_to_drive(file_path)
            print(f"✅ File downloaded to: {file_path}")
            
            if not os.path.exists(file_path):
                await update.message.reply_text(f"❌ File not found at: {file_path}")
                context.user_data['uploading'] = False
                return
            
            file_size = os.path.getsize(file_path)
            print(f"📊 File size: {file_size} bytes")
            
            session = SessionLocal()
            try:
                cards = []
                success_count = 0
                failed_count = 0
                total_lines = 0
                
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        total_lines += 1
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        delimiters = [',', '|', '\t', ' ']
                        delimiter = max(delimiters, key=lambda d: line.count(d))
                        parts = [p.strip() for p in line.split(delimiter)]
                        
                        print(f"📝 Line {line_num}: {len(parts)} parts, delimiter: '{delimiter}'")
                        
                        if len(parts) >= 4:
                            try:
                                card_number = parts[0]
                                expiry_month = parts[1]
                                expiry_year = parts[2]
                                cvv = parts[3]
                                
                                if not card_number.isdigit() or len(card_number) < 13 or len(card_number) > 19:
                                    failed_count += 1
                                    print(f"⚠️ Line {line_num}: Invalid card number")
                                    continue
                                
                                expiry = f"{expiry_month}/{expiry_year}"
                                bin_number = card_number[:6]
                                
                                # Default values
                                country = parts[4] if len(parts) > 4 and len(parts[4]) == 2 else 'US'
                                billing = parts[5] in ['1', 'True', 'yes', 'true'] if len(parts) > 5 else False
                                price = float(parts[6]) if len(parts) > 6 and parts[6].replace('.', '').isdigit() else DEFAULT_NAKED_PRICE
                                
                                card = Card(
                                    bin=bin_number,
                                    number=card_number,
                                    expiry=expiry,
                                    cvv=cvv,
                                    country=country,
                                    billing=billing,
                                    price=price,
                                    is_sold=False
                                )
                                cards.append(card)
                                success_count += 1
                            except (ValueError, IndexError) as e:
                                failed_count += 1
                                print(f"❌ Line {line_num} parse error: {e}")
                        else:
                            failed_count += 1
                            print(f"⚠️ Line {line_num}: Only {len(parts)} parts (need 4+)")
                
                print(f"✅ Cards to insert: {success_count}")
                print(f"❌ Failed lines: {failed_count}")
                
                if success_count > 0:
                    session.bulk_insert_mappings(Card, [c.__dict__ for c in cards])
                    session.commit()
                
                total = session.query(Card).count()
                available = session.query(Card).filter(Card.is_sold == False).count()
                
                await update.message.reply_text(
                    f"✅ **UPLOAD COMPLETE!**\n\n"
                    f"{'━'*40}\n"
                    f"📊 Cards Uploaded: {success_count}\n"
                    f"❌ Failed Lines: {failed_count}\n"
                    f"📈 Total Cards: {total}\n"
                    f"📉 Available: {available}\n"
                    f"{'━'*40}\n\n"
                    f"💰 Default Price: ${DEFAULT_NAKED_PRICE} USDT\n"
                    f"📁 File: `{filename}`\n"
                    f"📊 File Size: {file_size} bytes",
                    parse_mode="Markdown"
                )
                context.user_data['uploading'] = False
            
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                print(f"❌ Upload error: {error_msg}")
                if len(error_msg) > 3900:
                    error_msg = error_msg[:3900] + "...\n[Truncated]"
                await update.message.reply_text(f"❌ **Upload Error:**\n\n{error_msg}")
                context.user_data['uploading'] = False
                session.rollback()
            finally:
                session.close()
        
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            print(f"❌ Download error: {error_msg}")
            if len(error_msg) > 3900:
                error_msg = error_msg[:3900] + "...\n[Truncated]"
            await update.message.reply_text(f"❌ **Download Error:**\n\n{error_msg}")
            context.user_data['uploading'] = False
    else:
        await update.message.reply_text("❌ Unsupported file format. Use .txt or .csv")

# ============================================================================
# ⚙️ MAIN BOT SETUP
# ============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    logging.error(f"Exception while handling an update: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An error occurred. Please try again.\n\n"
                "If the problem persists, contact support."
            )
        except:
            pass

def main():
    """Main bot initialization"""
    print("✅ Starting bot...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("topup", topup))
    application.add_handler(CommandHandler("catalog", catalog))
    application.add_handler(CommandHandler("bin", bin_lookup))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("upload", admin_upload))
    application.add_handler(CommandHandler("edit_price", admin_edit_price))
    application.add_handler(CommandHandler("add_price", admin_add_price))
    application.add_handler(CommandHandler("export", admin_export))
    
    # Regex Handlers
    application.add_handler(MessageHandler(filters.Regex('^/bin '), handle_bin_search))
    application.add_handler(MessageHandler(filters.Regex('^/edit_price '), handle_edit_price))
    application.add_handler(MessageHandler(filters.Regex('^/add_price '), handle_add_price))
    
    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(menu_navigator, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(copy_usdt, pattern="^copy_usdt$"))
    application.add_handler(CallbackQueryHandler(confirm_deposit, pattern="^confirm_deposit$"))
    application.add_handler(CallbackQueryHandler(catalog_callback, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(buy_card_callback, pattern="^buy_card_"))
    application.add_handler(CallbackQueryHandler(confirm_buy_callback, pattern="^confirm_buy_"))
    application.add_handler(CallbackQueryHandler(country_callback, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(order_bin_callback, pattern="^order_bin_"))
    application.add_handler(CallbackQueryHandler(handle_quantity_selection, pattern="^qty_"))
    application.add_handler(CallbackQueryHandler(view_history, pattern="^view_history$"))
    application.add_handler(CallbackQueryHandler(admin_export, pattern="^admin_export$"))
    application.add_handler(CallbackQueryHandler(admin_upload, pattern="^admin_upload$"))
    
    # Message Handlers
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin_order))
    
    # Error Handler
    application.add_error_handler(error_handler)
    
    print("✅ Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
        print("✅ Bot started successfully!")
    except Exception as e:
        import traceback
        print(f"❌ Bot crashed: {e}")
        traceback.print_exc()
        sys.exit(1)

